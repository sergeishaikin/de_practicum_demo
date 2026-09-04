"""Fail-closed validator for the H1 OTel acceptance evidence.

The acceptance job runs the deterministic E2E three times - Collector disabled
(``off``), enabled (``on``), and enabled but stopped mid-run (``outage``) - and
claims the business result was identical. This script is the only thing allowed
to declare that claim PASS, and it declares nothing it did not check.

Two independent dimensions, not one:

  Correctness   per phase, the observed runtime contract equals the predicted one
  Transparency  the three phases observed *the same thing as each other*

The second is what makes telemetry non-interfering, and it is meaningful only
because the digests come from live Trino/Kafka/S3/Postgres reads taken before
teardown. The digests are recomputed here from the recorded payloads, so a
receipt cannot claim a hash its own contents do not produce.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PHASES = ("off", "on", "outage")

# The phase matrix is restated here on purpose. The capture step already refused
# to record a container whose state disagreed with what its caller declared - but
# nothing there checks that the *caller* declared the right thing. This is where
# "the outage phase actually stopped the Collector" is established.
PHASE_MATRIX = {
    "off": {"otel_enabled": False, "collector_outage": False},
    "on": {"otel_enabled": True, "collector_outage": False},
    "outage": {"otel_enabled": True, "collector_outage": True},
}

COLLECTOR = "de-demo-otel-collector"
REQUIRED_CONTAINERS = (
    COLLECTOR,
    "de-demo-iceberg-medallion",
    "de-demo-iceberg-writer",
    "de-demo-orders-streaming",
)
REQUIRED_STATS_FIELDS = ("Name", "CPUPerc", "MemUsage")


def canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def digest(payload: object) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def load_receipts(paths: list[str], errors: list[str]) -> dict[str, dict]:
    receipts: dict[str, dict] = {}
    for raw in paths:
        path = Path(raw)
        if not path.is_file() or path.stat().st_size == 0:
            errors.append(f"receipt missing or empty: {path}")
            continue
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"receipt is not valid JSON ({path}): {exc}")
            continue
        phase = receipt.get("phase")
        if phase not in PHASES:
            errors.append(f"receipt {path} has unknown phase {phase!r}")
            continue
        if phase in receipts:
            errors.append(f"phase {phase} supplied more than once")
            continue
        receipts[phase] = receipt
    missing = [phase for phase in PHASES if phase not in receipts]
    if missing:
        errors.append(f"missing receipts for phases: {missing}")
    return receipts


def check_phase(phase: str, receipt: dict, errors: list[str]) -> None:
    def fail(message: str) -> None:
        errors.append(f"[{phase}] {message}")

    for field, expected in PHASE_MATRIX[phase].items():
        if receipt.get(field) is not expected:
            fail(f"{field} is {receipt.get(field)!r}, expected {expected!r}")

    if receipt.get("pytest_e2e_passed") is not True:
        fail("pytest_e2e_passed is not True")

    duration = receipt.get("duration_seconds")
    if not isinstance(duration, (int, float)) or duration <= 0:
        fail(f"duration_seconds is not a positive number: {duration!r}")

    for field in ("otel_wal_bytes_before", "otel_wal_bytes_after"):
        value = receipt.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            fail(f"{field} is not a non-negative integer: {value!r}")

    observed = receipt.get("observed_contract")
    predicted = receipt.get("expected_contract")
    if not isinstance(observed, dict) or not observed:
        fail("observed_contract is absent or empty")
    elif digest(observed) != receipt.get("observed_contract_sha256"):
        fail("observed_contract_sha256 does not match observed_contract")
    if not isinstance(predicted, dict) or not predicted:
        fail("expected_contract is absent or empty")
    elif digest(predicted) != receipt.get("expected_contract_sha256"):
        fail("expected_contract_sha256 does not match expected_contract")

    if isinstance(observed, dict) and isinstance(predicted, dict):
        if observed != predicted:
            differing = {
                key: (predicted.get(key), observed.get(key))
                for key in set(predicted) | set(observed)
                if predicted.get(key) != observed.get(key)
            }
            fail(
                "observed contract diverges from expected "
                f"(expected, observed): {differing}"
            )

    snapshot = receipt.get("observed_gold_snapshot")
    if not isinstance(snapshot, list) or not snapshot:
        fail("observed_gold_snapshot is absent or empty")
    elif digest(snapshot) != receipt.get("observed_gold_sha256"):
        fail("observed_gold_sha256 does not match observed_gold_snapshot")

    check_resources(phase, receipt, errors)


def check_resources(phase: str, receipt: dict, errors: list[str]) -> None:
    def fail(message: str) -> None:
        errors.append(f"[{phase}] {message}")

    for stage in ("before", "after"):
        block = receipt.get(f"resources_{stage}")
        if not isinstance(block, dict):
            fail(f"resources_{stage} is absent")
            continue
        if block.get("phase") != phase or block.get("stage") != stage:
            fail(
                f"resources_{stage} is labelled "
                f"{block.get('phase')!r}/{block.get('stage')!r}"
            )
        containers = block.get("containers")
        if not isinstance(containers, dict):
            fail(f"resources_{stage}.containers is absent")
            continue
        for name in REQUIRED_CONTAINERS:
            record = containers.get(name)
            if not isinstance(record, dict):
                fail(f"resources_{stage} has no record for {name}")
                continue
            expected_state = record.get("expected_state")
            observed_state = record.get("observed_state")
            if expected_state not in ("running", "stopped"):
                fail(f"{name} ({stage}) has invalid expected_state {expected_state!r}")
                continue
            if observed_state != expected_state:
                fail(
                    f"{name} ({stage}) expected {expected_state}, "
                    f"observed {observed_state!r}"
                )
                continue
            stats = record.get("stats")
            if expected_state == "running":
                if not isinstance(stats, dict):
                    fail(f"{name} ({stage}) is running but carries no stats object")
                else:
                    absent = [f for f in REQUIRED_STATS_FIELDS if not stats.get(f)]
                    if absent:
                        fail(f"{name} ({stage}) stats missing fields {absent}")
            elif stats is not None:
                fail(f"{name} ({stage}) is stopped but carries stats")

        # The declaration itself has to be right, not merely self-consistent.
        collector = containers.get(COLLECTOR)
        if isinstance(collector, dict) and stage == "after":
            wanted = "stopped" if PHASE_MATRIX[phase]["collector_outage"] else "running"
            if collector.get("expected_state") != wanted:
                fail(
                    f"{COLLECTOR} (after) was declared "
                    f"{collector.get('expected_state')!r}, but phase {phase} "
                    f"requires {wanted!r}"
                )


def check_parity(
    receipts: dict[str, dict], require_git_sha: bool, errors: list[str]
) -> None:
    for field in ("observed_contract_sha256", "observed_gold_sha256"):
        seen = {phase: receipts[phase].get(field) for phase in PHASES}
        if len(set(seen.values())) != 1:
            errors.append(f"cross-phase parity mismatch on {field}: {seen}")

    shas = {phase: receipts[phase].get("git_sha", "") for phase in PHASES}
    if len(set(shas.values())) != 1:
        errors.append(f"phases did not run on one commit: {shas}")
    elif require_git_sha and not next(iter(shas.values())):
        errors.append("git_sha is empty; the evidence cannot be tied to a commit")

    # Three independent runs, not one receipt copied three times.
    run_ids = {phase: receipts[phase].get("run_id") for phase in PHASES}
    if len(set(run_ids.values())) != len(PHASES):
        errors.append(f"phases must be independent runs, got run_ids {run_ids}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipts", nargs="+", help="phase receipt JSON files")
    parser.add_argument("--require-git-sha", action="store_true")
    args = parser.parse_args(argv)

    errors: list[str] = []
    receipts = load_receipts(args.receipts, errors)
    if len(receipts) == len(PHASES):
        for phase in PHASES:
            check_phase(phase, receipts[phase], errors)
        check_parity(receipts, args.require_git_sha, errors)

    if errors:
        print("OTel acceptance evidence REJECTED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"observed_contract_sha256: {receipts['off']['observed_contract_sha256']}")
    print(f"observed_gold_sha256:     {receipts['off']['observed_gold_sha256']}")
    for phase in PHASES:
        receipt = receipts[phase]
        print(
            f"  {phase:<7} duration={receipt['duration_seconds']:.1f}s "
            f"wal={receipt['otel_wal_bytes_before']}"
            f"->{receipt['otel_wal_bytes_after']}B"
        )
    print("correctness (observed == expected, per phase): PASS")
    print("canonical_parity (off == on == outage, observed): PASS")
    print("resource_evidence: PASS")
    print("wal_evidence: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
