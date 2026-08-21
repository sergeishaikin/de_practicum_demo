"""Guards for the local runtime inventory and the contract it reports against.

The inventory exists so that nobody maintains hardware and image lists by hand.
That only helps if the script keeps working when Docker is stopped -- which is
exactly the state it is meant to describe -- and if it never captures a secret
while reading `.env`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import local_runtime_inventory as inv  # noqa: E402


def test_a_stopped_engine_is_reported_not_raised(monkeypatch):
    """The whole point: Docker being down is a finding, not a crash.

    A diagnostic that fails when Docker is stopped is useless precisely when it
    is needed, because "is Docker running?" is the question being asked.
    """
    monkeypatch.setattr(inv.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(
        inv, "_run", lambda command, timeout=60: (1, "", "Cannot connect to the daemon")
    )

    facts = inv.docker_facts()

    assert facts["cli_present"] is True
    assert facts["engine_reachable"] is False
    assert "startable state" in facts["note"]
    assert "not an unavailable dependency" in facts["note"]


def test_a_missing_docker_cli_is_distinguished_from_a_stopped_engine(monkeypatch):
    """Two different findings that must not collapse into one.

    "Not installed" is an environment limitation; "installed but stopped" is a
    thing to fix by starting it. Reporting them identically is the defect this
    whole change exists to remove.
    """
    monkeypatch.setattr(inv.shutil, "which", lambda name: None)
    facts = inv.docker_facts()
    assert facts["cli_present"] is False
    assert facts["engine_reachable"] is False
    assert "not on PATH" in facts["note"]


def test_collect_produces_a_report_when_docker_is_unreachable(monkeypatch):
    monkeypatch.setattr(
        inv, "docker_facts", lambda: {"cli_present": True, "engine_reachable": False}
    )
    inventory = inv.collect(".env")

    assert inventory["compose"]["skipped"]
    assert inventory["containers"] == []
    # Renders without raising, which is what the operator actually sees.
    assert "ACTION: start Docker Desktop" in inv.render(inventory)


def test_the_report_is_json_serialisable(monkeypatch):
    """It is written to disk as evidence; an unserialisable value fails late."""
    monkeypatch.setattr(
        inv, "docker_facts", lambda: {"cli_present": True, "engine_reachable": False}
    )
    json.dumps(inv.collect(".env"))


def test_only_image_variables_are_read_from_env_files(tmp_path, monkeypatch):
    """A diagnostic that reads `.env` must not capture credentials.

    The report is evidence and may be shared, so the parser is restricted to
    `*_IMAGE` keys by construction rather than by filtering afterwards.
    """
    env = tmp_path / ".env"
    env.write_text(
        "\n".join(
            [
                "POSTGRES_IMAGE=postgres:15",
                "POSTGRES_PASSWORD=hunter2",
                "AIRFLOW_JWT_SECRET=very-secret",
                "MINIO_ROOT_PASSWORD=minio123",
                "AWS_SECRET_ACCESS_KEY=abcdef",
                "# a comment",
                "MALFORMED_LINE",
            ]
        ),
        encoding="utf-8",
    )

    pins = inv._image_pins(env)

    assert pins == {"POSTGRES_IMAGE": "postgres:15"}
    blob = json.dumps(pins)
    for secret in ("hunter2", "very-secret", "minio123", "abcdef"):
        assert secret not in blob


def test_image_pin_drift_reports_floating_local_tags(tmp_path, monkeypatch):
    """The difference between a local run and a CI run, made visible.

    Compose references these images as `${VAR}`, so the committed-compose guard
    cannot see a floating tag that lives in a developer's `.env`.
    """
    monkeypatch.setattr(inv, "REPO_ROOT", tmp_path)
    (tmp_path / ".env.example").write_text(
        "ICEBERG_REST_IMAGE=tabulario/iceberg-rest@sha256:abc\n"
        "TRINO_IMAGE=trinodb/trino@sha256:def\n",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "ICEBERG_REST_IMAGE=tabulario/iceberg-rest:latest\n"
        "TRINO_IMAGE=trinodb/trino@sha256:def\n",
        encoding="utf-8",
    )

    drift = inv.image_pin_drift()

    assert drift["local_env_present"] is True
    assert drift["floating_locally"] == ["ICEBERG_REST_IMAGE"]
    assert [d["variable"] for d in drift["differences"]] == ["ICEBERG_REST_IMAGE"]


def test_matching_pins_report_no_drift(tmp_path, monkeypatch):
    """Proof the drift check can come out clean, or a passing report proves
    nothing about a machine that genuinely matches CI."""
    monkeypatch.setattr(inv, "REPO_ROOT", tmp_path)
    for name in (".env", ".env.example"):
        (tmp_path / name).write_text(
            "TRINO_IMAGE=trinodb/trino@sha256:def\n", encoding="utf-8"
        )

    drift = inv.image_pin_drift()

    assert drift["differences"] == []
    assert drift["floating_locally"] == []


def test_the_committed_example_env_pins_every_image_by_digest():
    """`.env.example` is the reference CI resolves against.

    `test_committed_compose_pins_every_image` guards the Compose files, where
    these appear as variables, so nothing else checks this file.
    """
    pins = inv._image_pins(REPO_ROOT / ".env.example")
    assert pins, "no *_IMAGE variables found in .env.example"

    unpinned = sorted(name for name, value in pins.items() if "@sha256:" not in value)
    assert not unpinned, (
        "these images are not digest-pinned in the committed .env.example: "
        f"{unpinned}"
    )


@pytest.mark.parametrize(
    "document, required",
    [
        (
            "docs/LOCAL-ENVIRONMENT.md",
            [
                "A stopped Docker daemon is not an unavailable dependency",
                "Measured snapshot",
                "scripts/local_runtime_inventory.py",
            ],
        ),
        (
            "AGENTS.md",
            [
                "Local runtime availability",
                "does NOT mean that Docker-dependent verification is",
            ],
        ),
        (
            "docs/TESTING.md",
            ["Local-first live verification policy", "Runtime surface per marker"],
        ),
        ("docs/DEVELOPMENT.md", ["Container runtime", "docs/LOCAL-ENVIRONMENT.md"]),
    ],
)
def test_the_execution_contract_is_actually_written_down(document, required):
    """The contract is the deliverable; a moved heading must fail loudly.

    Without this, the rule could be silently edited away and every check here
    would still pass while agents went back to skipping live tests.
    """
    text = (REPO_ROOT / document).read_text(encoding="utf-8")
    missing = [phrase for phrase in required if phrase not in text]
    assert not missing, f"{document} no longer states: {missing}"


def test_the_generated_inventory_is_not_committed():
    """Generated runtime state is evidence, not a source of truth.

    A committed inventory becomes a second place the truth lives, and it is
    stale the moment the machine changes.
    """
    import subprocess

    result = subprocess.run(
        ["git", "ls-files", "artifacts/local-environment"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "", (
        "the generated runtime inventory is tracked by git: " f"{result.stdout.strip()}"
    )
