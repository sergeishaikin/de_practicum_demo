"""Evaluate an M5 cutover evidence bundle.

Usage:
    python scripts/verify_m5_cutover.py --evidence artifacts/m5/cutover.json

The evidence file is intentionally explicit and reviewable. It can be
produced by a live cutover test or an operations job after querying progress
and ``marts.lakehouse_metrics``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "iceberg"))

from common.cutover import evaluate_cutover_gate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    config = {
        name: os.getenv(name, "")
        for name in ("SILVER_MODE", "GOLD_SOURCE", "SHADOW_COMPARE")
    }
    result = evaluate_cutover_gate(config, evidence)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
