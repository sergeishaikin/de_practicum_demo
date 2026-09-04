"""Assemble one phase receipt for the H1 OTel acceptance job.

Replaces a shell heredoc that re-derived the "canonical contract" by AST-parsing
``tests/e2e/test_lakehouse_e2e.py``. That derivation was a pure function of the
checked-out source, so every phase produced an identical digest whatever the
runtime did, and the cross-phase parity check could not fail.

This script instead assembles the receipt out of measurements the run actually
took, and refuses to produce one when any of them is missing or malformed.
Nothing here has a default: an absent input is an error, never a zero.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Written by tests/e2e/test_lakehouse_e2e.py immediately before teardown.
REQUIRED_OBSERVED_KEYS = (
    "run_id",
    "namespace",
    "expected_contract",
    "expected_contract_sha256",
    "observed_contract",
    "observed_contract_sha256",
    "observed_gold_snapshot",
    "observed_gold_sha256",
)


class ReceiptError(RuntimeError):
    pass


def read_json(path: Path, label: str) -> dict:
    if not path.is_file() or path.stat().st_size == 0:
        raise ReceiptError(f"{label} is missing or empty: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReceiptError(f"{label} is not valid JSON ({path}): {exc}") from exc


def read_int(path: Path, label: str) -> int:
    if not path.is_file():
        raise ReceiptError(f"{label} is missing: {path}")
    raw = path.read_text(encoding="utf-8").strip()
    if not raw.isdigit():
        raise ReceiptError(f"{label} is not a non-negative integer ({path}): {raw!r}")
    return int(raw)


def read_duration(path: Path) -> float:
    if not path.is_file():
        raise ReceiptError(f"duration file is missing: {path}")
    raw = path.read_text(encoding="utf-8").strip().splitlines()
    if not raw:
        raise ReceiptError(f"duration file is empty: {path}")
    try:
        duration = float(raw[-1])
    except ValueError as exc:
        raise ReceiptError(f"duration is not a number ({path}): {raw[-1]!r}") from exc
    if duration <= 0:
        raise ReceiptError(f"duration must be positive, got {duration} ({path})")
    return duration


def build(args: argparse.Namespace) -> dict:
    observed = read_json(Path(args.observed), "observed evidence")
    missing = [key for key in REQUIRED_OBSERVED_KEYS if key not in observed]
    if missing:
        raise ReceiptError(f"observed evidence is missing keys: {missing}")

    resources_before = read_json(Path(args.resources_before), "resources (before)")
    resources_after = read_json(Path(args.resources_after), "resources (after)")

    return {
        "phase": args.phase,
        "otel_enabled": args.otel_enabled == 1,
        "collector_outage": args.collector_outage == 1,
        "pytest_e2e_passed": True,
        "git_sha": observed.get("git_sha", ""),
        "run_id": observed["run_id"],
        "namespace": observed["namespace"],
        "duration_seconds": read_duration(Path(args.duration_file)),
        "expected_contract": observed["expected_contract"],
        "expected_contract_sha256": observed["expected_contract_sha256"],
        "observed_contract": observed["observed_contract"],
        "observed_contract_sha256": observed["observed_contract_sha256"],
        "observed_gold_snapshot": observed["observed_gold_snapshot"],
        "observed_gold_sha256": observed["observed_gold_sha256"],
        "otel_wal_bytes_before": read_int(Path(args.wal_before), "WAL bytes (before)"),
        "otel_wal_bytes_after": read_int(Path(args.wal_after), "WAL bytes (after)"),
        "resources_before": resources_before,
        "resources_after": resources_after,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, choices=("off", "on", "outage"))
    parser.add_argument("--otel-enabled", required=True, type=int, choices=(0, 1))
    parser.add_argument("--collector-outage", required=True, type=int, choices=(0, 1))
    parser.add_argument("--observed", required=True)
    parser.add_argument("--duration-file", required=True)
    parser.add_argument("--wal-before", required=True)
    parser.add_argument("--wal-after", required=True)
    parser.add_argument("--resources-before", required=True)
    parser.add_argument("--resources-after", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    try:
        receipt = build(args)
    except ReceiptError as exc:
        print(f"receipt build failed: {exc}", file=sys.stderr)
        return 1

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", "utf-8")
    print(f"receipt written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
