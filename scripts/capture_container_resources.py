"""Capture container resource evidence as validated JSON, or fail.

The H1 OTel acceptance job used to record resource usage with::

    docker stats --format '{{.Name}} {{.CPUPerc}} {{.MemUsage}}' "$c" >> out || true

so ``Error response from daemon: No such container`` landed in the evidence file
as ordinary text and the receipt still reported ``resource_delta: RECORDED``.
A measurement that cannot fail is not evidence.

This script instead states, per container, what the phase expects and what the
runtime shows, and exits non-zero when the two disagree or when a required
measurement cannot be taken. ``stats: null`` is only ever written for a
container the caller declared *should* be stopped, and only after
``docker inspect`` confirmed it is not running - so "no stats" and "stopped on
purpose" are never the same record.

Usage::

    python scripts/capture_container_resources.py \
        --phase off --stage before --output otel-off-resources-before.json \
        --expect de-demo-otel-collector=running \
        --expect de-demo-iceberg-writer=running
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

RUNNING = "running"
STOPPED = "stopped"
ABSENT = "absent"

# The fields a docker stats record must carry for the receipt to mean anything.
REQUIRED_STATS_FIELDS = ("Name", "CPUPerc", "MemUsage")


def _docker(*args: str) -> tuple[int, str, str]:
    result = subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=60
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def observe_state(container: str) -> str:
    """`running`, `stopped`, or `absent` - never `unknown`."""
    code, out, _ = _docker("inspect", "--format", "{{.State.Running}}", container)
    if code != 0:
        return ABSENT
    return RUNNING if out == "true" else STOPPED


def observe_stats(container: str) -> dict:
    """Parsed docker stats, or raise. Text that is not JSON is a failure here."""
    code, out, err = _docker(
        "stats", "--no-stream", "--format", "{{json .}}", container
    )
    if code != 0:
        raise RuntimeError(f"docker stats failed for {container}: {err or out}")
    try:
        stats = json.loads(out)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"docker stats for {container} did not return JSON: {out!r}"
        ) from exc
    if not isinstance(stats, dict):
        raise RuntimeError(f"docker stats for {container} is not an object: {out!r}")
    missing = [field for field in REQUIRED_STATS_FIELDS if not stats.get(field)]
    if missing:
        raise RuntimeError(
            f"docker stats for {container} is missing {missing}: {out!r}"
        )
    return stats


def capture(expectations: dict[str, str]) -> tuple[dict, list[str]]:
    containers: dict[str, dict] = {}
    errors: list[str] = []
    for container, expected_state in sorted(expectations.items()):
        observed_state = observe_state(container)
        record = {
            "expected_state": expected_state,
            "observed_state": observed_state,
            "stats": None,
        }
        if observed_state != expected_state:
            errors.append(
                f"{container}: expected {expected_state}, observed {observed_state}"
            )
        elif expected_state == RUNNING:
            try:
                record["stats"] = observe_stats(container)
            except RuntimeError as exc:
                errors.append(str(exc))
        containers[container] = record
    return containers, errors


def parse_expectation(raw: str) -> tuple[str, str]:
    name, _, state = raw.partition("=")
    if not name or state not in (RUNNING, STOPPED):
        raise argparse.ArgumentTypeError(
            f"--expect must be NAME=running or NAME=stopped, got {raw!r}"
        )
    return name, state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--stage", required=True, choices=("before", "after"))
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--expect",
        required=True,
        action="append",
        type=parse_expectation,
        metavar="NAME=running|stopped",
    )
    args = parser.parse_args(argv)

    containers, errors = capture(dict(args.expect))
    payload = {
        "phase": args.phase,
        "stage": args.stage,
        "containers": containers,
    }
    # Written even on failure: the mismatch itself is the evidence worth keeping.
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", "utf-8")

    if errors:
        for error in errors:
            print(f"resource evidence failure: {error}", file=sys.stderr)
        return 1
    print(f"resource evidence captured for {args.phase}/{args.stage}: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
