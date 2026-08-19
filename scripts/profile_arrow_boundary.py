"""Measure the Arrow/Python boundary in the B2 Silver projection.

Usage:
    python scripts/profile_arrow_boundary.py --out artifacts/phase-04/04-arrow-boundary-profile.json

Measures four steps separately, plus the sequence as the medallion actually
executes it, over synthetic rows. Touches no catalog, database, object store or
broker: every function measured here is pure, so the measurement needs no stack
and cannot perturb one.

The numbers bound the boundary's cost. They do not predict it — see the `limits`
block in the emitted artifact.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import pyarrow as pa

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "iceberg"))

from b2_spike import collapse_delta, resolve_against_current  # noqa: E402

# Mirrors medallion._SILVER_TYPES. Duplicated rather than imported because
# importing the medallion pulls in pyiceberg, boto3 and a catalog module for a
# measurement that needs none of them; the copy is asserted against the real
# schema by the medallion's own tests, not by this one-off tool.
SILVER_TYPES: dict[str, pa.DataType] = {
    "order_id": pa.string(),
    "customer": pa.string(),
    "amount": pa.float64(),
    "country": pa.string(),
    "status": pa.string(),
    "event_time": pa.timestamp("us"),
    "kafka_timestamp": pa.timestamp("us"),
    "kafka_partition": pa.int32(),
    "kafka_offset": pa.int64(),
    "event_date": pa.date32(),
    "business_version": pa.int64(),
}
SILVER_COLUMNS = tuple(SILVER_TYPES)

COUNTRIES = ("BR", "US", "DE", "FR", "JP")
STATUSES = ("created", "paid", "shipped", "delivered")
EPOCH = datetime(2026, 8, 8, 12, 0, 0)


def _row(order_id: str, version: int, offset: int) -> dict[str, Any]:
    """A Silver row whose payload is a deterministic function of key and version.

    Determinism matters for more than reproducibility: two rows sharing an
    `order_id` and a `business_version` must share a payload, or `collapse_delta`
    raises FF-14 and the measurement times a raise instead of the resolution
    loop it is meant to measure.
    """

    seed = (hash(order_id) & 0xFFFF) + version
    return {
        "order_id": order_id,
        "customer": f"customer-{seed % 9973}",
        "amount": float(seed % 100_000) / 100.0,
        "country": COUNTRIES[seed % len(COUNTRIES)],
        "status": STATUSES[seed % len(STATUSES)],
        "event_time": EPOCH + timedelta(seconds=seed % 86_400),
        "kafka_timestamp": EPOCH + timedelta(seconds=seed % 86_400),
        "kafka_partition": 0,
        "kafka_offset": offset,
        "event_date": date(2026, 8, 8),
        "business_version": version,
    }


def _rows_to_silver(rows: list[dict[str, Any]]) -> pa.Table:
    """The medallion's Python-to-Arrow reconstruction, called the same way."""

    return pa.table(
        {
            name: pa.array([row.get(name) for row in rows], type=SILVER_TYPES[name])
            for name in SILVER_COLUMNS
        }
    )


def build_case(size: int, keys: int, overlap: float) -> dict[str, Any]:
    """Build one measurement case: a delta, and the current state it meets.

    `keys` distinct business keys are spread over `size` delta rows, so a delta
    carrying repeats exercises the collapse rather than skipping it. `overlap` is
    the share of those keys that already exist in current Silver, at a lower
    version — the case that produces work rather than a no-op.
    """

    keys = max(1, min(keys, size))
    delta_rows = [
        _row(f"order-{index % keys:09d}", 1 + index // keys, index)
        for index in range(size)
    ]
    overlapping = int(keys * overlap)
    current_rows = [
        _row(f"order-{index:09d}", 1, index) for index in range(overlapping)
    ]
    return {
        "delta_rows": delta_rows,
        "current_rows": current_rows,
        "delta_table": _rows_to_silver(delta_rows),
        "current_table": _rows_to_silver(current_rows),
    }


def _median_ms(fn: Callable[[], Any], repeats: int) -> tuple[float, Any]:
    samples: list[float] = []
    result: Any = None
    for _ in range(repeats):
        start = time.perf_counter()
        result = fn()
        samples.append((time.perf_counter() - start) * 1000.0)
    return statistics.median(samples), result


def measure(size: int, keys: int, overlap: float, repeats: int) -> dict[str, Any]:
    case = build_case(size, keys, overlap)
    delta_table = case["delta_table"]
    current_table = case["current_table"]
    delta_rows = case["delta_rows"]
    current_rows = case["current_rows"]

    arrow_to_python_delta, incoming = _median_ms(delta_table.to_pylist, repeats)
    arrow_to_python_current, current = _median_ms(current_table.to_pylist, repeats)
    collapse, collapsed = _median_ms(lambda: collapse_delta(incoming), repeats)
    resolve, resolved = _median_ms(
        lambda: resolve_against_current(current, incoming), repeats
    )
    python_to_arrow, _ = _median_ms(lambda: _rows_to_silver(resolved), repeats)

    # The sequence the medallion actually runs (iceberg_medallion.py:609-630):
    # to_pylist on the delta, to_pylist on the current scan, collapse_delta, then
    # resolve_against_current - which collapses the same delta a second time -
    # and finally the reconstruction. Reported separately because it is the only
    # figure corresponding to work a cycle executes end to end. It is not larger
    # than the per-step sum: `resolve_against_current` measured on its own
    # already pays the second collapse, so the sum covers both.
    def production_sequence() -> pa.Table:
        seq_incoming = delta_table.to_pylist()
        seq_current = current_table.to_pylist()
        collapse_delta(seq_incoming)
        seq_resolved = resolve_against_current(seq_current, seq_incoming)
        return _rows_to_silver(seq_resolved)

    sequence, _ = _median_ms(production_sequence, repeats)

    steps = {
        "arrow_to_python_delta_ms": arrow_to_python_delta,
        "arrow_to_python_current_ms": arrow_to_python_current,
        "collapse_delta_ms": collapse,
        "resolve_against_current_ms": resolve,
        "python_to_arrow_ms": python_to_arrow,
    }
    return {
        "delta_rows": size,
        "distinct_keys": min(keys, size),
        "overlap_ratio_with_current": overlap,
        "current_rows": len(current_rows),
        "repeats": repeats,
        "steps_ms_median": steps,
        "steps_sum_ms": sum(steps.values()),
        "production_sequence_ms_median": sequence,
        "collapse_runs_per_cycle": 2,
        "rows_out": {
            "collapsed": len(collapsed),
            "resolved": len(resolved),
            "delta_rows_in": len(delta_rows),
        },
    }


def build_profile(sizes: list[int], overlap: float, key_ratio: float) -> dict[str, Any]:
    measurements = []
    for size in sizes:
        keys = max(1, int(size * key_ratio))
        # Repeats fall as size grows: enough samples for a median without
        # letting the largest sweep dominate the run.
        repeats = 21 if size <= 100 else 7 if size <= 10_000 else 3
        measurements.append(measure(size, keys, overlap, repeats))
    return {
        "schema_version": 1,
        "phase": "04-medallion-telemetry-and-redundant-work-elimination",
        "plan": "04-10",
        "requirement": "PRF-01",
        "executed_as": "openspec change profile-arrow-python-boundary",
        "environment": {
            "python": sys.version.split()[0],
            "pyarrow": pa.__version__,
            "platform": platform.platform(),
            "processor": platform.processor() or "unknown",
            "machine": platform.machine(),
        },
        "measured_steps": [
            "arrow_to_python_delta: delta.to_pylist()",
            "arrow_to_python_current: current_scan.to_arrow().to_pylist()",
            "collapse_delta",
            "resolve_against_current",
            "python_to_arrow: _rows_to_silver reconstruction",
            "production_sequence: the five above in the medallion's call order",
        ],
        "measurements": measurements,
        "limits": [
            "Synthetic rows over pure functions. This bounds the boundary's cost; it does not predict production cost.",
            "Does not reproduce cache behaviour under a real Iceberg scan, real payload distributions, or the Arrow buffer layout a catalog read produces.",
            "Wall time on a shared developer machine. Medians reduce noise; they do not remove it.",
            "Measured on one host, one interpreter and one pyarrow build. No cross-platform claim is made.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--sizes",
        type=int,
        nargs="+",
        default=[1, 100, 10_000, 1_000_000],
        help="delta sizes to sweep, in rows",
    )
    parser.add_argument(
        "--overlap",
        type=float,
        default=0.5,
        help="share of delta keys already present in current Silver",
    )
    parser.add_argument(
        "--key-ratio",
        type=float,
        default=0.5,
        help="distinct business keys as a share of delta rows",
    )
    args = parser.parse_args()

    profile = build_profile(args.sizes, args.overlap, args.key_ratio)
    # The `decision` block is written by the change that consumes this profile,
    # not by the measurement. Carry it across a re-run so re-measuring cannot
    # silently delete a recorded disposition; a reader can tell it is stale by
    # comparing its `measured_at` against the measurements beside it.
    if args.out.exists():
        previous = json.loads(args.out.read_text(encoding="utf-8"))
        if "decision" in previous:
            profile["decision"] = previous["decision"]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps({"measurements": len(profile["measurements"]), "out": str(args.out)})
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
