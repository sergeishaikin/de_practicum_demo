"""Repository contracts for the Phase 03B warehouse dbt project."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "dbt" / "warehouse"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_warehouse_dbt_runtime_is_pinned_and_separate() -> None:
    assert (PROJECT / "dbt_project.yml").exists()
    assert (PROJECT / "profiles.yml.example").exists()
    requirements = (
        (PROJECT / "requirements.in").read_text(encoding="utf-8").splitlines()
    )
    assert requirements == ["dbt-core==1.12.2", "dbt-postgres==1.11.0"]
    locked = (PROJECT / "requirements.txt").read_text(encoding="utf-8")
    assert "dbt-core==1.12.2" in locked
    assert "dbt-postgres==1.11.0" in locked


def test_sources_keep_airflow_owned_boundaries_explicit() -> None:
    sources = (PROJECT / "models" / "sources.yml").read_text(encoding="utf-8")
    for source_name in ("staging", "core"):
        assert f"name: {source_name}" in sources
    for table_name in ("orders", "order_items", "order_payments", "customers"):
        assert f"name: {table_name}" in sources
    assert "owner:airflow" in sources


def test_staging_sources_declare_load_recency_freshness() -> None:
    """Freshness is only a gate if *every* staging source carries it, and it is
    only *narrow* if `core.*` does not.

    A staging table without thresholds is silently skipped by dbt — no error, no
    warning — so a fifth table added later without freshness would quietly open a
    hole. The count-of-four is what catches that. The core half is what keeps the
    guarantee narrow: `core.*` is a derived projection, not an arrival point, and
    declaring freshness there would claim something this design does not.
    """

    sources = (PROJECT / "models" / "sources.yml").read_text(encoding="utf-8")
    staging, _, core = sources.partition("- name: core")

    assert staging.count("loaded_at_field: loaded_at") == 4
    assert staging.count("warn_after") == 4
    assert staging.count("error_after") == 4

    assert "loaded_at_field" not in core
    assert "freshness" not in core
    assert "warn_after" not in core

    # The design uses a physical column, never a derived query.
    assert "loaded_at_query" not in sources


def test_marts_preserve_existing_relation_names_and_sql_boundaries() -> None:
    expected = {
        "v_order_items_wide": "v_order_items_wide",
        "v_sales_daily": "v_sales_daily",
        "v_customer_state_daily": "v_customer_state_daily",
        "v_reconcile_sales_daily": "v_reconcile_sales_daily",
    }
    for model, alias in expected.items():
        sql = (PROJECT / "models" / "marts" / f"{model}.sql").read_text(
            encoding="utf-8"
        )
        assert f"alias='{alias}'" in sql
        assert "{{ config(" in sql
    assert "source('core', 'order_items')" in (
        PROJECT / "models" / "marts" / "v_sales_daily.sql"
    ).read_text(encoding="utf-8")
    reconcile = (
        PROJECT / "models" / "marts" / "v_reconcile_sales_daily.sql"
    ).read_text(encoding="utf-8")
    assert "source('staging', 'orders')" in reconcile
    assert "ref('v_sales_daily')" in reconcile


def test_quality_contracts_and_selectors_are_present() -> None:
    schema = (PROJECT / "models" / "marts" / "schema.yml").read_text(encoding="utf-8")
    for contract_model in (
        "v_order_items_wide",
        "v_sales_daily",
        "v_customer_state_daily",
        "v_reconcile_sales_daily",
    ):
        assert f"name: {contract_model}" in schema
    assert schema.count("enforced: true") == 4
    for test_name in (
        "mart_reconciliation.sql",
        "order_items_wide_grain.sql",
        "payment_reconciliation.sql",
        # Property/invariant tests: these hold on *any* data, unlike the
        # reconciliation tests which assert today's rows agree.
        "reconcile_arithmetic_consistency.sql",
        "sales_daily_orders_within_items.sql",
        "order_items_wide_preserves_item_count.sql",
        "customer_state_rolls_up_to_sales_daily.sql",
    ):
        assert (PROJECT / "tests" / test_name).exists()

    # Reusable generic tests, kept local because the project carries no packages.
    for macro_name in ("non_negative.sql", "composite_unique.sql"):
        assert (PROJECT / "macros" / macro_name).exists()

    # Generic test arguments must stay nested under `arguments:` - the top-level
    # form is deprecated in dbt 1.12 and warns on every parse.
    assert "arguments:" in schema
    assert "columns: [order_id, order_item_id]" in schema
    selectors = (PROJECT / "selectors.yml").read_text(encoding="utf-8")
    assert "warehouse_contracts" in selectors
    assert "warehouse_reconciliation" in selectors


def test_unit_tests_pin_the_mart_transformation_semantics() -> None:
    """The mart SQL must be covered by fixture-driven unit tests, not only by
    data tests that need a populated warehouse."""

    definitions = (PROJECT / "models" / "marts" / "unit_tests.yml").read_text(
        encoding="utf-8"
    )
    expected_models = {
        "order_items_wide_keeps_items_without_a_matching_order": "v_order_items_wide",
        "order_items_wide_enriches_every_item_of_its_order": "v_order_items_wide",
        "sales_daily_counts_orders_distinctly_and_sums_money_per_day": "v_sales_daily",
        "reconcile_sales_daily_reports_both_sides_of_the_full_join": "v_reconcile_sales_daily",
        "reconcile_sales_daily_ignores_cross_batch_ingest_dates": "v_reconcile_sales_daily",
        "customer_state_daily_partitions_each_day_by_state": "v_customer_state_daily",
        "sales_daily_sums_money_exactly_not_in_floating_point": "v_sales_daily",
        "sales_daily_produces_no_rows_for_an_empty_source": "v_sales_daily",
        "reconcile_sales_daily_is_empty_when_both_sides_are_empty": "v_reconcile_sales_daily",
    }
    cases = definitions.split("  - name: ")[1:]
    assert len(cases) == len(expected_models)
    for case in cases:
        name = case.splitlines()[0].strip()
        assert name in expected_models, f"unknown unit test: {name}"
        assert f"model: {expected_models[name]}" in case
        assert "expect:" in case and "rows:" in case

    by_name = {case.splitlines()[0].strip(): case for case in cases}

    # The LEFT JOIN guard is only a guard if core.orders is mocked empty and the
    # payment columns are asserted NULL rather than merely absent.
    orphan = by_name["order_items_wide_keeps_items_without_a_matching_order"]
    assert "input: source('core', 'orders')\n        rows: []" in orphan
    assert "order_payment_value: null" in orphan.split("expect:")[1]

    # The cross-batch guard is only a guard if the ingest dates actually differ
    # between the mocked staging header and its item.
    cross_batch = by_name["reconcile_sales_daily_ignores_cross_batch_ingest_dates"]
    given, expected = cross_batch.split("expect:")
    assert {"'2026-01-01'", "'2026-01-02'"} <= set(
        line.split("ingest_date: ")[1].strip()
        for line in given.splitlines()
        if "ingest_date: " in line
    )
    assert "source_gross_sales: 0.00" in expected


def test_integration_fixture_runs_the_production_core_rebuild() -> None:
    """The staging -> core -> marts -> reconciliation check must go through the
    real rebuild transform, not a hand-written core insert."""

    seed = (ROOT / "tests" / "fixtures" / "warehouse" / "seed_staging.sql").read_text(
        encoding="utf-8"
    )
    assert "marts.pipeline_runs" in seed, "destructive seed is missing its guard"
    assert "insert into core." not in seed.lower()

    assertions = (
        ROOT / "tests" / "fixtures" / "warehouse" / "assert_marts.sql"
    ).read_text(encoding="utf-8")
    for relation in (
        "core.orders",
        "marts.v_sales_daily",
        "marts.v_customer_state_daily",
        "marts.v_order_items_wide",
        "marts.v_reconcile_sales_daily",
    ):
        assert relation in assertions

    workflow = read(".github/workflows/ci-pr.yml")
    assert "tests/fixtures/warehouse/seed_staging.sql" in workflow
    assert "db/pipeline_sql/10_rebuild_core.sql" in workflow
    assert "tests/fixtures/warehouse/assert_marts.sql" in workflow
    assert "insert into core.orders values" not in workflow

    invariant = PROJECT / "tests" / "customer_state_rolls_up_to_sales_daily.sql"
    assert "v_customer_state_daily" in invariant.read_text(encoding="utf-8")


def test_replay_parity_is_asserted_against_the_production_rebuild() -> None:
    """Reprocessing the same staging batch must not change the business result.
    That is what makes an Airflow retry or manual re-trigger safe."""

    fixtures = ROOT / "tests" / "fixtures" / "warehouse"
    snapshot = (fixtures / "replay_snapshot.sql").read_text(encoding="utf-8")
    assert "create schema replay_check" in snapshot
    # The snapshot must capture core *and* every mart, or a divergence could hide.
    for relation in (
        "core.orders",
        "core.order_items",
        "marts.v_sales_daily",
        "marts.v_customer_state_daily",
        "marts.v_order_items_wide",
        "marts.v_reconcile_sales_daily",
    ):
        assert relation in snapshot

    parity = (fixtures / "assert_replay_parity.sql").read_text(encoding="utf-8")
    # Symmetric difference: rows that appeared and rows that vanished.
    assert "appeared on replay" in parity
    assert "lost on replay" in parity
    # EXCEPT is set-based, so duplicated rows need an explicit count guard.
    assert "row count changed" in parity
    assert "{%" not in parity, "this file runs through psql, not dbt"

    workflow = read(".github/workflows/ci-pr.yml")
    assert "tests/fixtures/warehouse/replay_snapshot.sql" in workflow
    assert "tests/fixtures/warehouse/assert_replay_parity.sql" in workflow
    # The replay must go through the real transform, twice.
    assert workflow.count("db/pipeline_sql/10_rebuild_core.sql") >= 2


def test_staging_load_timestamp_fixtures_are_guarded_and_deterministic() -> None:
    """Two failure modes, both worse than a failing test.

    A stray local run of the backdate fixture against a real warehouse would
    block the marts DAG for two hours with no obvious cause, which is why both
    mutating fixtures carry the same `marts.pipeline_runs` emptiness guard the
    seed uses. And a fixture that produced staleness by *waiting* rather than by
    writing would make the entire freshness layer flaky — the point of a
    test-controlled column is that staleness is deterministic.
    """

    fixtures = ROOT / "tests" / "fixtures" / "warehouse"

    def body(name: str) -> str:
        text = (fixtures / name).read_text(encoding="utf-8")
        # Strip comments so a later header edit cannot invalidate a count.
        return "\n".join(
            line for line in text.splitlines() if not line.strip().startswith("--")
        )

    backdate = body("backdate_staging_loaded_at.sql")
    reset = body("reset_staging_loaded_at.sql")
    one_batch = body("assert_loaded_at_is_one_batch.sql")

    tables = ("orders", "order_items", "order_payments", "customers")

    for name, sql in (("backdate", backdate), ("reset", reset)):
        assert "marts.pipeline_runs" in sql, f"{name} fixture is missing its guard"
        assert "raise exception" in sql, f"{name} fixture guard does not abort"
        # One transaction, so all four tables share one timestamp.
        assert sql.count("begin;") == 1, f"{name} is not a single transaction"
        assert sql.count("commit;") == 1, f"{name} is not a single transaction"

    assert backdate.count("interval '3 hours'") == 4
    for table in tables:
        assert f"update stg.{table} set loaded_at" in backdate
    assert reset.count("set loaded_at = now()") == 4

    # Staleness is written, never waited for. Asserted against the executable
    # SQL rather than the whole file: the headers legitimately discuss why there
    # is no sleep, and prose must not be able to fail a behavioural check.
    # "sleep" subsumes "pg_sleep".
    for name, sql in (
        ("backdate", backdate),
        ("reset", reset),
        ("one_batch", one_batch),
    ):
        assert "sleep" not in sql.lower(), f"{name} waits instead of writing"

    assert "'loaded_at differs across staging tables'" in one_batch
    assert "having count(*) <> 1" in one_batch
    assert "{%" not in one_batch, "this file runs through psql, not dbt"

    # R8: the linter's scope is deliberate. These fixtures are not in it.
    workflow = read(".github/workflows/ci-pr.yml")
    assert (
        "sqlfluff lint dbt/warehouse/models dbt/warehouse/tests dbt/models" in workflow
    )


def test_tier1_tests_persist_their_failure_rows() -> None:
    """A red Tier-1 test must say *which* rows broke, not just that something did."""

    for name in (
        "mart_reconciliation.sql",
        "payment_reconciliation.sql",
        "order_items_wide_grain.sql",
        "customer_state_rolls_up_to_sales_daily.sql",
    ):
        sql = (PROJECT / "tests" / name).read_text(encoding="utf-8")
        assert "store_failures=true" in sql, f"{name} discards its failure rows"

    # Payment reconciliation must compare per order, not as one global SUM -
    # a global total passes whenever two errors cancel out.
    payments = (PROJECT / "tests" / "payment_reconciliation.sql").read_text(
        encoding="utf-8"
    )
    assert "group by order_id, ingest_date" in payments
    assert "full join" in payments


def test_generate_schema_name_keeps_the_legacy_marts_relation_names() -> None:
    """The macro deliberately discards `target.schema`, which is the opposite of
    dbt's default. That is load-bearing: `dags/warehouse_dbt.py` reads the mart
    views by literal `marts.*` name and publishes Assets with `marts/<view>`
    URIs, so dbt's default `<target>_<custom>` prefix would break both."""

    macro = (PROJECT / "macros" / "generate_schema_name.sql").read_text(
        encoding="utf-8"
    )
    assert "custom_schema_name | trim if custom_schema_name else target.schema" in macro

    # The consumers that make this non-negotiable.
    dag = read("dags/warehouse_dbt.py")
    for literal in ("marts.v_order_items_wide", "marts.v_sales_daily"):
        assert literal in dag
    assert '"marts/v_order_items_wide"' in dag or "marts/v_order_items_wide" in dag

    # And the trade-off is documented rather than silently accepted.
    doc = read("docs/warehouse/W1-dbt-ownership.md")
    assert "generate_schema_name" in doc

    # Stronger evidence when a parsed manifest is available: every mart model must
    # land in `marts`, unprefixed. Skipped in the fast suite, where no dbt run has
    # happened yet.
    manifest_path = PROJECT / "target" / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    marts = {
        node["name"]: node
        for node in manifest.get("nodes", {}).values()
        if node.get("resource_type") == "model"
    }
    assert marts, "manifest contains no models"
    for name, node in marts.items():
        assert node["schema"] == "marts", f"{name} resolved to {node['schema']!r}"


def test_core_rebuild_transaction_remains_airflow_owned() -> None:
    source = read("dags/warehouse_orders.py")
    assert '_execute_sql_file(conn, SQL_DIR / "10_rebuild_core.sql")' in source
    assert "warehouse_orders_ingestion()" in source
    assert not source.rstrip().endswith("warehouse_marts_validation()")


def test_cosmos_warehouse_dag_uses_watcher_and_explicit_publication() -> None:
    source = read("dags/warehouse_dbt.py")
    assert "ExecutionMode.WATCHER" in source
    assert 'dbt_id="warehouse_marts_validation"' not in source
    assert 'dag_id="warehouse_marts_validation"' in source
    assert "render_config=RenderConfig(emit_datasets=False)" in source
    assert "publish_mart_assets" in source
    assert "PIPELINE_AUDIT_ASSET" in source
    assert "get_current_context" in source


def test_marts_dag_gates_dbt_build_on_source_freshness() -> None:
    """The import path is the load-bearing assertion here.

    `DbtSourceLocalOperator` is not re-exported from `cosmos.operators` in
    astronomer-cosmos 1.15.0, so the shorter, obvious-looking import raises
    ImportError at parse time and takes down the entire DagBag — not just this
    DAG. The fast suite would never notice on its own, because it does not import
    Airflow or Cosmos at all. Hence a source-text assertion.
    """

    source = read("dags/warehouse_dbt.py")

    assert "from cosmos.operators.local import DbtSourceLocalOperator" in source
    assert (
        "from cosmos.operators import DbtDocsOperator, DbtSourceLocalOperator"
        not in source
    )
    assert 'task_id="check_source_freshness"' in source
    # Source-level wiring only. Whether the rendered producer edge exists in a
    # real DagBag is proven by observing a live one, not by this assertion.
    assert "check_source_freshness >> dbt_group" in source

    # Each of these would weaken the gate rather than break it, which is the
    # dangerous kind of regression: the DAG would still import and still be
    # green.
    #   source_rendering_behavior -> activates Cosmos' experimental Watcher
    #                                freshness path, which this design rejects
    #   warn_error                -> promotes the advisory warn into an error and
    #                                collapses the two thresholds into one
    #   on_warning_callback       -> a warn-level hook that gates nothing, so it
    #                                reads as protection while providing none
    #   skip_exit_code            -> dbt only exits 0, 1 or 2, so the default is
    #                                unreachable; changing it adds an
    #                                unexplained parameter
    for weakening in (
        "source_rendering_behavior",
        "warn_error",
        "on_warning_callback",
        "skip_exit_code",
    ):
        assert weakening not in source, f"{weakening} weakens the freshness gate"

    # Keeps the documentation from drifting back behind the code.
    w1 = read("docs/warehouse/W1-dbt-ownership.md")
    assert "Not adopted, deliberately: dbt source freshness" not in w1
    assert (
        "Prevent downstream certification from consuming staging "
        "whose most recent successful load is outside the permitted age." in w1
    )
