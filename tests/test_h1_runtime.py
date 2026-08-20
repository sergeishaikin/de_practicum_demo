from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from scripts import verify_maintenance_dag as maintenance_verifier
from scripts import verify_warehouse_asset_flow as asset_verifier
from scripts.validate_runtime_config import validate


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_clean_environment_pins_external_images_and_has_no_latest_tags() -> None:
    env = read(".env.example")
    image_lines = [
        line
        for line in env.splitlines()
        if line.endswith("\n") is False and "_IMAGE=" in line
    ]
    assert image_lines
    assert all(
        re.search(r"@sha256:[0-9a-f]{64}$", line.split("=", 1)[1])
        for line in image_lines
    )
    assert "latest" not in env


def test_postgres_health_means_reachable_over_tcp() -> None:
    """Health must mean ready by the path dependents actually use.

    `airflow-db-init` waits for `condition: service_healthy` and then connects to
    `de-demo-postgres:5432` over TCP. A socket-only `pg_isready` answers "ready"
    while initdb's temporary server is running on a fresh volume, before anything
    listens on 5432 - so the dependent started and died with connection refused,
    visible only on a cold start and therefore only in the H1 clean run.

    This pins the probe rather than the string: a future simplification back to a
    socket check fails here instead of in a 180-minute clean rebuild.
    """

    compose = read("docker-compose.yml")
    postgres = compose.split("de-demo-postgres:", 1)[1].split("airflow-db-init:", 1)[0]
    probe = postgres.split("healthcheck:", 1)[1].split("interval:", 1)[0]

    assert "pg_isready" in probe
    assert "-h 127.0.0.1" in probe
    assert "-p 5432" in probe


def test_h1_dbt_expectation_matches_the_semantic_project() -> None:
    """The pinned dbt total must equal what the project actually declares.

    H1 asserts `PASS=n ... TOTAL=n` so that tests cannot vanish unnoticed. That
    guard only works while n is right: the semantic project gained two unit
    tests, the workflow still demanded 26, and a run where dbt reported
    `PASS=28 ERROR=0` failed the step. Counting the sources here means the next
    added test fails in this suite, in a second, rather than 40 minutes into a
    clean rebuild.

    The count is a declaration-shape heuristic over the project YAML, calibrated
    against dbt's own reported total (26 data tests + 2 unit tests = 28). It is
    deliberately noisy rather than clever: a YAML style it does not recognise
    fails here loudly instead of silently drifting from the workflow.
    """

    workflow = read(".github/workflows/ci-h1-clean.yml")
    pinned = re.search(r"PASS=(\d+) \.\*ERROR=0 \.\*TOTAL=(\d+)", workflow)
    assert pinned, "H1 no longer pins a dbt test total"
    passes, total = (int(group) for group in pinned.groups())
    assert passes == total

    declared = len(
        re.findall(r"^\s+- name:", read("dbt/models/semantic/unit_tests.yml"), re.M)
    )
    sources_and_models = read("dbt/models/sources.yml") + read(
        "dbt/models/semantic/semantic.yml"
    )
    data_tests = sum(
        len(re.findall(pattern, sources_and_models))
        for pattern in (r"- not_null", r"- unique", r"- accepted_values", r"not_null\]")
    )
    data_tests += len(list(Path("dbt/tests").glob("*.sql")))

    assert total == data_tests + declared, (
        f"H1 pins TOTAL={total}; the project declares "
        f"{data_tests} data tests + {declared} unit tests"
    )


def test_trino_is_not_ready_while_it_is_still_starting() -> None:
    """`/v1/info` returns 200 during startup, so the payload decides readiness.

    H1's bootstrap treated any 200 as ready and the next statement died with
    `Trino server is still initializing`, twice in a row. The probe now requires
    the server to say it finished starting.
    """

    import importlib
    import io
    import json as json_module
    import sys
    from contextlib import contextmanager

    # Imported the way the script runs, with scripts/ on the path - its own
    # `from validate_runtime_config import ...` depends on that.
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        bootstrap_stack = importlib.import_module("bootstrap_stack")
    finally:
        sys.path.pop(0)

    @contextmanager
    def responding(payload: dict, status: int = 200):
        body = io.BytesIO(json_module.dumps(payload).encode("utf-8"))
        body.status = status
        yield body

    def urlopen_returning(payload: dict, status: int = 200):
        def fake(url, timeout=None):
            return responding(payload, status)

        return fake

    original = bootstrap_stack.urllib.request.urlopen
    try:
        for payload, status, expected in [
            ({"starting": True}, 200, False),
            ({"starting": False}, 200, True),
            ({}, 200, False),
            ({"starting": False}, 503, False),
        ]:
            bootstrap_stack.urllib.request.urlopen = urlopen_returning(payload, status)
            assert bootstrap_stack._trino_ready("http://trino/v1/info") is expected, (
                payload,
                status,
            )
    finally:
        bootstrap_stack.urllib.request.urlopen = original


def test_every_postgres_readiness_probe_is_tcp() -> None:
    """No readiness probe may ask the socket whether the server is up.

    During initdb on a fresh volume the image runs a temporary server on the
    socket. A socket probe answers "ready" against it, the caller then connects,
    and the temporary server is already shutting down - which is exactly the
    `FATAL: the database system is shutting down` that broke the warehouse CI job
    and the `Connection refused` that broke H1's airflow-db-init. Both consumers
    speak TCP, so every probe must too.
    """

    sources = [
        "docker-compose.yml",
        "docker-compose.local-airflow.yml",
        ".github/workflows/ci-pr.yml",
    ]
    socket_probes = [
        f"{path}:{number}"
        for path in sources
        for number, line in enumerate(read(path).splitlines(), start=1)
        if "pg_isready" in line and "-h " not in line
    ]

    assert not socket_probes, f"socket-only pg_isready probe: {socket_probes}"


def test_no_bind_mount_targets_a_path_inside_another_mount() -> None:
    """A file mount nested inside a read-write directory mount mutates the checkout.

    Docker materialises a missing bind-mount target before mounting over it. When
    the target resolves inside another host mount, that placeholder is created in
    the host checkout - root-owned and empty - and nothing running as the checkout
    owner can replace it afterwards. H1 proved it: `dbt/profiles.yml` appeared as
    `root:root`, 0 bytes, born at stack start, and `cp` then failed with
    Permission denied.

    The rule is structural, so it is checked structurally rather than by naming
    the one pair that caused it.
    """

    compose = read("docker-compose.yml")
    targets = []
    for line in compose.splitlines():
        entry = line.strip()
        if not entry.startswith("- ./"):
            continue
        parts = entry[2:].split(":")
        if len(parts) < 2 or not parts[1].startswith("/"):
            continue
        targets.append((parts[0], parts[1]))

    directory_mounts = [target for source, target in targets if not Path(source).suffix]
    nested = [
        (source, target)
        for source, target in targets
        for directory in directory_mounts
        if target != directory and target.startswith(directory + "/")
    ]

    assert not nested, f"bind mount target nested inside another mount: {nested}"


def test_spark_runtime_has_baked_jars_and_no_runtime_package_resolution() -> None:
    compose = read("docker-compose.extended.yml")
    e2e = read("tests/e2e/test_lakehouse_e2e.py")
    lock = read("spark/h1-runtime-jars.lock")

    assert "spark-submit-h1" in compose
    assert "--packages" not in compose
    assert "spark.jars.ivy" not in compose
    assert "spark-submit-h1" in e2e
    assert "--packages" not in e2e
    assert "spark-sql-kafka-0-10_2.13|4.2.0" in lock
    assert "org.postgresql|postgresql|42.7.4" in lock


def test_custom_build_services_have_explicit_versioned_image_tags() -> None:
    compose = read("docker-compose.extended.yml")
    for image in (
        "de-practicum-demo-spark:4.2.0-h1",
        "de-practicum-demo-jupyter:spark420-h1",
        "de-practicum-demo-iceberg:0.11.1-h1",
        "de-practicum-demo-observability:0.22.1-h1",
        "de-practicum-demo-orders-producer:0.1.0",
    ):
        assert image in compose


def test_airflow_3_local_runtime_contract() -> None:
    dockerfile = read("airflow.Dockerfile")
    compose = read("docker-compose.yml")
    local_compose = read("docker-compose.local-airflow.yml")

    assert "apache/airflow:3.3.1-python3.12@sha256:" in dockerfile
    for content in (compose, local_compose):
        assert "airflow-db-init:" in content
        assert "condition: service_completed_successfully" in content
        assert "AIRFLOW__CORE__EXECUTOR: LocalExecutor" in content
        assert 'AIRFLOW__CORE__PARALLELISM: "4"' in content
        assert 'AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_ALL_ADMINS: "True"' in content
        assert 'AIRFLOW__API__INSTANCE_NAME: "DE Practicum · Local"' in content
        assert "AIRFLOW__API__SECRET_KEY:" in content
        assert "AIRFLOW__API_AUTH__JWT_SECRET:" in content
        assert "postgresql+psycopg2://${AIRFLOW_DB_USER:-airflow}:" in content
        assert "sqlite:////opt/airflow/airflow.db" not in content
        assert "127.0.0.1:${AIRFLOW_HOST_PORT:-18085}:8080" in content
        assert "- standalone" in content
        assert "SequentialExecutor" not in content
        assert "AIRFLOW__WEBSERVER__" not in content
        assert "airflow users create" not in content
        assert "airflow webserver" not in content

    init = read("db/init/006_airflow_metadata.sh")
    assert "CREATE ROLE" in init
    assert "CREATE DATABASE" in init
    assert "ALTER DATABASE" in init


def test_e2e_ad_hoc_container_inherits_runtime_credentials() -> None:
    e2e = read("tests/e2e/test_lakehouse_e2e.py")

    assert "f\"POSTGRES_PASSWORD={PG['password']}\"" in e2e
    assert 'f"AWS_SECRET_ACCESS_KEY={SECRET_KEY}"' in e2e
    assert '"POSTGRES_PASSWORD=app"' not in e2e
    assert '"AWS_SECRET_ACCESS_KEY=minio123"' not in e2e


def test_clean_dbt_runtime_serializes_sqlite_catalog_commits() -> None:
    profile = read("dbt/profiles.yml.example")
    workflow = read(".github/workflows/ci-h1-clean.yml")

    assert "threads: 1" in profile
    assert "dbt run --profiles-dir . --select semantic --threads 1" in workflow


def test_clean_workflow_exports_deploy_credentials_to_host_checks() -> None:
    workflow = read(".github/workflows/ci-h1-clean.yml")

    assert "source .env" in workflow
    assert "AWS_SECRET_ACCESS_KEY=${MINIO_ROOT_PASSWORD}" in workflow
    assert "DWH_PASSWORD=${POSTGRES_PASSWORD}" in workflow
    assert "DBT_TRINO_PORT=${TRINO_HOST_PORT}" in workflow


def test_pytest_entrypoint_has_an_explicit_repository_import_root() -> None:
    pytest_config = read("pytest.ini")

    assert "pythonpath = ." in pytest_config


def test_runtime_dependency_pins_are_shared_at_the_python_arrow_boundary() -> None:
    host = read("pyproject.toml")
    iceberg = read("iceberg/requirements.in")

    assert "pyiceberg==0.11.1" in host
    assert "pyarrow==21.0.0" in host
    assert "pyiceberg[pyarrow]==0.11.1" in iceberg
    assert "pyarrow==21.0.0" in iceberg


def test_python_dependencies_are_locked_and_installed_with_uv() -> None:
    assert read(".python-version").strip() == "3.12"
    assert 'required-version = "==0.12.5"' in read("pyproject.toml")
    assert "version = 1" in read("uv.lock")

    lock_pairs = (
        ("airflow.requirements.in", "airflow.requirements.txt"),
        ("dbt/requirements.in", "dbt/requirements.txt"),
        ("iceberg/requirements.in", "iceberg/requirements.txt"),
        ("jupyter/requirements.in", "jupyter/requirements.txt"),
        ("kafka/producer/requirements.in", "kafka/producer/requirements.txt"),
        ("observability/requirements.in", "observability/requirements.txt"),
        ("spark/requirements.in", "spark/requirements.txt"),
    )
    for source, lock in lock_pairs:
        assert read(source).strip()
        assert "autogenerated by uv" in read(lock)
        assert "--hash=sha256:" in read(lock)

    dockerfiles = (
        "airflow.Dockerfile",
        "iceberg/Dockerfile",
        "jupyter/Dockerfile",
        "kafka/producer/Dockerfile",
        "observability/Dockerfile",
        "spark/Dockerfile",
    )
    for dockerfile in dockerfiles:
        content = read(dockerfile)
        assert "ghcr.io/astral-sh/uv:0.12.5@sha256:" in content
        assert "/bin/uv pip install" in content
        assert "--require-hashes" in content
        assert "pip install" not in content.replace("/bin/uv pip install", "")

    assert "mamba create" not in read("jupyter/Dockerfile")
    assert not (ROOT / "superset" / "Dockerfile").exists()
    assert not (ROOT / "superset" / "requirements.in").exists()
    assert not (ROOT / "superset" / "requirements.txt").exists()


def test_config_validator_rejects_placeholders_and_unpinned_images() -> None:
    values = {
        "POSTGRES_USER": "app",
        "POSTGRES_PASSWORD": "change-me",
        "POSTGRES_DB": "dwh",
        "AIRFLOW_DB_NAME": "airflow_meta",
        "AIRFLOW_DB_USER": "airflow",
        "AIRFLOW_DB_PASSWORD": "secret",
        "MINIO_ROOT_USER": "minio",
        "MINIO_ROOT_PASSWORD": "secret",
        "SUPERSET_SECRET_KEY": "secret",
        "AIRFLOW_API_SECRET_KEY": "secret",
        "AIRFLOW_JWT_SECRET": "secret",
        **{
            key: "repo:latest"
            for key in (
                "POSTGRES_IMAGE",
                "MINIO_IMAGE",
                "METABASE_IMAGE",
                "KAFKA_IMAGE",
                "KAFKA_UI_IMAGE",
                "ICEBERG_REST_IMAGE",
                "TRINO_IMAGE",
                "PROMETHEUS_IMAGE",
                "GRAFANA_IMAGE",
                "SUPERSET_IMAGE",
            )
        },
        **{
            key: "1234"
            for key in (
                "POSTGRES_HOST_PORT",
                "AIRFLOW_HOST_PORT",
                "MINIO_API_PORT",
                "MINIO_CONSOLE_PORT",
                "KAFKA_HOST_PORT",
                "ICEBERG_REST_PORT",
                "TRINO_HOST_PORT",
                "PROMETHEUS_HOST_PORT",
                "GRAFANA_HOST_PORT",
            )
        },
    }

    errors = validate(values, profile="clean")
    assert any("placeholder secret" in error for error in errors)
    assert any("pinned by digest" in error for error in errors)


def test_h1_bootstrap_ci_and_docs_are_present() -> None:
    workflow = read(".github/workflows/ci-h1-clean.yml")
    docs = read("docs/runtime/H1-reproducible-runtime.md")

    for marker in (
        "--volumes",
        "--pull always",
        "integration",
        "iceberg-writer iceberg-medallion",
        "e2e",
        "dbt test",
        "Prometheus",
    ):
        assert marker in workflow
    for marker in ("baked", "bootstrap", "rollback", "D-3a", "Ivy"):
        assert marker in docs


def test_pipeline_provenance_migration_is_additive_and_bootstrapped() -> None:
    base = read("db/init/004_smoke_objects.sql")
    migration = read("db/init/007_pipeline_runs_ingestion_provenance.sql")
    bootstrap = read("scripts/bootstrap_stack.py")

    assert "run_id varchar primary key" in base
    assert "ingestion_run_id varchar" in base
    assert "marts_run_id" not in base + migration
    assert "add column if not exists ingestion_run_id varchar" in migration
    assert "create index if not exists idx_pipeline_runs_ingestion_run_id" in migration
    assert "create unique index" not in migration.lower()
    assert "007_pipeline_runs_ingestion_provenance.sql" in bootstrap
    assert 'values["POSTGRES_DB"]' in bootstrap
    dag = read("dags/warehouse_orders.py")
    assert 'os.getenv("DWH_PASSWORD", "app")' not in dag
    assert '_required_env("DWH_PASSWORD")' in dag


def test_stg_loaded_at_migration_is_additive_and_bootstrapped() -> None:
    """Two failure modes make these assertions load-bearing.

    `db/init/` runs only on an empty PostgreSQL data directory, so without the
    bootstrap replay this change works on a fresh stack and silently does
    nothing on every existing one — the freshness gate would then read a column
    that is not there. And the DDL must stay additive, because `stg.*` is a live
    relation in every developer's warehouse; a destructive form here is not a
    failed test, it is lost data.
    """

    migration = read("db/init/008_stg_loaded_at.sql")
    bootstrap = read("scripts/bootstrap_stack.py")
    # A future header edit must not be able to change a count assertion.
    body = "\n".join(
        line for line in migration.splitlines() if not line.strip().startswith("--")
    )

    for table in ("orders", "order_items", "order_payments", "customers"):
        assert f"alter table if exists stg.{table}" in body
    assert (
        body.count(
            "add column if not exists loaded_at timestamptz not null default now()"
        )
        == 4
    )
    # now() is transaction-start time, so one batch yields one timestamp across
    # all four tables. clock_timestamp() would vary per row and break that.
    assert "clock_timestamp" not in body
    assert "drop" not in body.lower()
    assert "create unique index" not in body.lower()

    assert "008_stg_loaded_at.sql" in bootstrap
    # The 007 contract must not regress while adding 008.
    assert "007_pipeline_runs_ingestion_provenance.sql" in bootstrap
    assert 'values["POSTGRES_DB"]' in bootstrap

    # Naming loaded_at in a COPY column list would make PostgreSQL demand it in
    # the CSV and break every load. PostgreSQL must supply the default instead.
    assert "loaded_at" not in read("dags/warehouse_orders.py")
    # The column arrives only through the additive migration, so the two files
    # cannot drift into competing definitions.
    assert "loaded_at" not in read("db/init/002_stg_tables.sql")


def test_warehouse_asset_verifier_generates_unique_source_run_ids() -> None:
    first = asset_verifier.make_run_id()
    second = asset_verifier.make_run_id()

    assert first != second
    assert re.fullmatch(r"warehouse_ingestion_verify_\d{8}T\d{12}Z_[0-9a-f]{12}", first)


def test_warehouse_asset_verifier_triggers_only_ingestion_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_airflow(*args: str, timeout: int = 90) -> str:
        calls.append((args, timeout))
        return ""

    monkeypatch.setattr(asset_verifier, "_airflow", fake_airflow)
    run_id = "warehouse_ingestion_verify_exact"

    asset_verifier.trigger_ingestion(run_id)

    assert calls == [
        (("dags", "trigger", "-r", run_id, "warehouse_orders_ingestion"), 90)
    ]
    assert all("warehouse_marts_validation" not in args for args, _ in calls)


def _valid_core_event_rows(source_run_id: str) -> list[list[str]]:
    return [
        [
            "101",
            asset_verifier.CORE_ORDER_ITEMS_URI,
            '{"row_count": 1149}',
            asset_verifier.INGESTION_DAG,
            asset_verifier.CORE_PUBLISH_TASK,
            source_run_id,
        ],
        [
            "102",
            asset_verifier.CORE_ORDERS_URI,
            '{"row_count": 1000}',
            asset_verifier.INGESTION_DAG,
            asset_verifier.CORE_PUBLISH_TASK,
            source_run_id,
        ],
    ]


def _expected_core_counts() -> dict[str, int]:
    return {
        asset_verifier.CORE_ORDER_ITEMS_URI: 1149,
        asset_verifier.CORE_ORDERS_URI: 1000,
    }


def test_warehouse_asset_verifier_accepts_exact_core_events() -> None:
    source = "warehouse_ingestion_verify_exact"

    accepted, _, events = asset_verifier.classify_core_events(
        source, _valid_core_event_rows(source), _expected_core_counts()
    )

    assert accepted is True
    assert events[asset_verifier.CORE_ORDERS_URI] == {
        "event_id": 102,
        "extra": {"row_count": 1000},
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda rows: rows[:1],
        lambda rows: rows + [rows[0]],
        lambda rows: [rows[0], [*rows[1][:-1], "wrong-run"]],
        lambda rows: [rows[0], [*rows[1][:2], '{"run_id":"bad"}', *rows[1][3:]]],
        lambda rows: [rows[0], [*rows[1][:4], "wrong.task", rows[1][5]]],
        lambda rows: [[*rows[0][:2], '{"row_count":true}', *rows[0][3:]], rows[1]],
        lambda rows: [
            [*rows[0][:2], '{"row_count":1000}', *rows[0][3:]],
            [*rows[1][:2], '{"row_count":1149}', *rows[1][3:]],
        ],
    ],
    ids=[
        "missing",
        "duplicate",
        "wrong-source",
        "run-id-extra",
        "wrong-task",
        "boolean-count",
        "swapped-counts",
    ],
)
def test_warehouse_asset_verifier_rejects_invalid_core_events(mutate) -> None:
    source = "warehouse_ingestion_verify_exact"
    rows = mutate(_valid_core_event_rows(source))

    accepted, _, events = asset_verifier.classify_core_events(
        source, rows, _expected_core_counts()
    )

    assert accepted is False
    assert events == {}


def test_warehouse_asset_verifier_unpauses_only_asset_consumer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_airflow(*args: str, timeout: int = 90) -> str:
        calls.append((args, timeout))
        if args[:2] == ("dags", "list"):
            return "warehouse_orders_ingestion\nwarehouse_marts_validation"
        return ""

    monkeypatch.setattr(asset_verifier, "_airflow", fake_airflow)

    asset_verifier.ensure_dags_ready()

    assert (("dags", "unpause", "warehouse_marts_validation"), 90) in calls
    assert (("dags", "unpause", "warehouse_orders_ingestion"), 90) not in calls


def test_warehouse_asset_verifier_accepts_only_one_asset_triggered_downstream() -> None:
    rows = [["asset_triggered__exact", "success", "asset_triggered", "ASSET", "102"]]

    accepted, _, run_id, state = asset_verifier.classify_downstream(102, rows)

    assert accepted is True
    assert run_id == "asset_triggered__exact"
    assert state == "success"


@pytest.mark.parametrize(
    "rows",
    [
        [
            ["asset_triggered__a", "success", "asset_triggered", "ASSET", "102"],
            ["asset_triggered__b", "success", "asset_triggered", "ASSET", "102"],
        ],
        [["manual__fake", "success", "manual", "CLI", "102"]],
        [["asset_triggered__wrong", "success", "asset_triggered", "ASSET", "999"]],
    ],
    ids=["duplicate", "manual-substitute", "wrong-event"],
)
def test_warehouse_asset_verifier_rejects_downstream_substitutes(rows) -> None:
    accepted, _, run_id, state = asset_verifier.classify_downstream(102, rows)

    assert accepted is False
    assert run_id is None
    assert state is None


def test_warehouse_asset_verifier_requires_exact_audit_provenance() -> None:
    source = "warehouse_ingestion_verify_exact"
    downstream = "asset_triggered__exact"
    valid = [
        [downstream, source, "success", "1000", "1149", "1149", "463", "0", "0", "0.00"]
    ]

    accepted, _ = asset_verifier.classify_audit(source, downstream, valid)
    wrong_source = [valid[0].copy()]
    wrong_source[0][1] = "wrong-source"
    rejected, _ = asset_verifier.classify_audit(source, downstream, wrong_source)

    assert accepted is True
    assert rejected is False


def test_warehouse_asset_verifier_stops_on_failed_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(asset_verifier, "dag_run_state", lambda *_: "failed")

    with pytest.raises(asset_verifier.VerificationError, match="failed"):
        asset_verifier.wait_for_success("warehouse_orders_ingestion", "manual__failed")


def test_warehouse_asset_verifier_times_out_without_retriggering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    monkeypatch.setattr(asset_verifier, "TIMEOUT_SECONDS", 0)
    monkeypatch.setattr(
        asset_verifier, "trigger_ingestion", lambda run_id: calls.append(run_id)
    )

    with pytest.raises(asset_verifier.VerificationError, match="timed out"):
        asset_verifier.wait_for_success("warehouse_orders_ingestion", "manual__missing")

    assert calls == []


def test_warehouse_asset_verifier_stops_on_failed_downstream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        asset_verifier,
        "downstream_rows",
        lambda *_: [
            ["asset_triggered__failed", "failed", "asset_triggered", "ASSET", "102"]
        ],
    )

    with pytest.raises(asset_verifier.VerificationError, match="failed"):
        asset_verifier.wait_for_downstream(102)


def test_maintenance_verifier_generates_unique_exact_run_ids() -> None:
    first = maintenance_verifier.make_run_id()
    second = maintenance_verifier.make_run_id()

    assert first != second
    assert re.fullmatch(r"maintenance_verify_\d{8}T\d{12}Z_[0-9a-f]{12}", first)


def test_maintenance_verifier_passes_run_id_to_one_trigger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_airflow(*args: str, timeout: int = 90) -> subprocess.CompletedProcess:
        calls.append((args, timeout))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(maintenance_verifier, "_airflow", fake_airflow)
    run_id = "maintenance_verify_20260815T220000000000Z_0123456789ab"

    maintenance_verifier.trigger(run_id)

    assert calls == [(("dags", "trigger", "-r", run_id, "lakehouse_maintenance"), 90)]


def test_maintenance_verifier_queries_only_the_exact_run_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}
    run_id = "maintenance_verify_exact"
    expected_rows = [(run_id, "bronze.orders", "ok")]

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, params: tuple[str]) -> None:
            captured["sql"] = sql
            captured["params"] = params

        def fetchall(self):
            return expected_rows

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def cursor(self):
            return Cursor()

    monkeypatch.setattr(
        maintenance_verifier.psycopg2, "connect", lambda **_kwargs: Connection()
    )

    rows = maintenance_verifier.audit_rows_for_run(run_id)

    assert rows == expected_rows
    assert "where run_id = %s" in captured["sql"]
    assert captured["params"] == (run_id,)


def test_maintenance_verifier_accepts_one_success_row_per_exact_target() -> None:
    run_id = "exact_run"
    rows = [
        (run_id, table, "noop" if index == 0 else "ok")
        for index, table in enumerate(sorted(maintenance_verifier.EXPECTED_TABLES))
    ]

    accepted, _ = maintenance_verifier.classify_audit_rows(run_id, rows)

    assert accepted is True


@pytest.mark.parametrize(
    "rows",
    [
        [
            ("old_run", table, "ok")
            for table in sorted(maintenance_verifier.EXPECTED_TABLES)
        ],
        [
            ("exact_run", table, "ok")
            for table in sorted(maintenance_verifier.EXPECTED_TABLES)[:2]
        ],
        [
            ("exact_run", "bronze.orders", "ok"),
            ("exact_run", "bronze.orders", "ok"),
            ("exact_run", "silver.orders_clean", "ok"),
        ],
        [
            ("exact_run", table, "ok")
            for table in sorted(maintenance_verifier.EXPECTED_TABLES)
        ]
        + [("exact_run", "gold.unexpected", "ok")],
        [
            (
                ("exact_run", table, "failed:expire_snapshots")
                if table == "bronze.orders"
                else ("exact_run", table, "ok")
            )
            for table in sorted(maintenance_verifier.EXPECTED_TABLES)
        ],
    ],
    ids=["stale-equivalent", "missing", "duplicate", "extra", "failed"],
)
def test_maintenance_verifier_rejects_non_exact_rows(
    rows: list[tuple[str, str, str]],
) -> None:
    accepted, _ = maintenance_verifier.classify_audit_rows("exact_run", rows)

    assert accepted is False


def _exact_audit_rows(run_id: str) -> list[tuple[str, str, str]]:
    return [(run_id, table, "ok") for table in maintenance_verifier.EXPECTED_TABLES]


def test_maintenance_verifier_main_triggers_once_and_requires_exact_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = "maintenance_verify_exact"
    triggers: list[str] = []
    monkeypatch.setattr(maintenance_verifier, "ensure_dag_ready", lambda: None)
    monkeypatch.setattr(maintenance_verifier, "make_run_id", lambda: run_id)
    monkeypatch.setattr(maintenance_verifier, "trigger", triggers.append)
    monkeypatch.setattr(maintenance_verifier, "dag_run_state", lambda _run: "success")
    monkeypatch.setattr(
        maintenance_verifier,
        "audit_rows_for_run",
        lambda _run: _exact_audit_rows(run_id),
    )

    assert maintenance_verifier.main() == 0
    assert triggers == [run_id]


@pytest.mark.parametrize(
    ("state", "rows"),
    [
        ("failed", []),
        ("success", [("maintenance_verify_exact", "bronze.orders", "ok")]),
    ],
    ids=["failed-dagrun", "successful-dagrun-invalid-audit"],
)
def test_maintenance_verifier_main_fails_closed_for_terminal_invalid_results(
    monkeypatch: pytest.MonkeyPatch,
    state: str,
    rows: list[tuple[str, str, str]],
) -> None:
    run_id = "maintenance_verify_exact"
    triggers: list[str] = []
    monkeypatch.setattr(maintenance_verifier, "ensure_dag_ready", lambda: None)
    monkeypatch.setattr(maintenance_verifier, "make_run_id", lambda: run_id)
    monkeypatch.setattr(maintenance_verifier, "trigger", triggers.append)
    monkeypatch.setattr(maintenance_verifier, "dag_run_state", lambda _run: state)
    monkeypatch.setattr(maintenance_verifier, "audit_rows_for_run", lambda _run: rows)

    assert maintenance_verifier.main() == 1
    assert triggers == [run_id]


def test_maintenance_verifier_main_times_out_without_retriggering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = "maintenance_verify_exact"
    triggers: list[str] = []
    clock = iter([0.0, 0.0, 2.0])
    monkeypatch.setattr(maintenance_verifier, "ensure_dag_ready", lambda: None)
    monkeypatch.setattr(maintenance_verifier, "make_run_id", lambda: run_id)
    monkeypatch.setattr(maintenance_verifier, "trigger", triggers.append)
    monkeypatch.setattr(maintenance_verifier, "TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(maintenance_verifier.time, "time", lambda: next(clock))
    monkeypatch.setattr(maintenance_verifier.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(maintenance_verifier, "dag_run_state", lambda _run: "running")
    monkeypatch.setattr(maintenance_verifier, "audit_rows_for_run", lambda _run: [])

    assert maintenance_verifier.main() == 1
    assert triggers == [run_id]


def test_maintenance_verifier_main_propagates_malformed_state_uncertainty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = "maintenance_verify_exact"
    triggers: list[str] = []
    monkeypatch.setattr(maintenance_verifier, "ensure_dag_ready", lambda: None)
    monkeypatch.setattr(maintenance_verifier, "make_run_id", lambda: run_id)
    monkeypatch.setattr(maintenance_verifier, "trigger", triggers.append)
    monkeypatch.setattr(
        maintenance_verifier,
        "dag_run_state",
        lambda _run: (_ for _ in ()).throw(RuntimeError("malformed DagRun state")),
    )

    with pytest.raises(RuntimeError, match="malformed DagRun state"):
        maintenance_verifier.main()
    assert triggers == [run_id]
