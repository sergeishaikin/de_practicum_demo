"""Reconcile one proven S1.2A.1 no-op without deleting its manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ICEBERG_DIR = REPO_ROOT / "iceberg"
if str(ICEBERG_DIR) not in sys.path:
    sys.path.insert(0, str(ICEBERG_DIR))

from medallion.iceberg_medallion import get_catalog, get_fs  # noqa: E402
from medallion.legacy_outbox_reconciliation import (  # noqa: E402
    reconcile_inflight_noop,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--load-id", required=True)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    result = reconcile_inflight_noop(get_catalog(), get_fs(), args.load_id)
    payload = json.dumps(result, sort_keys=True, indent=2, default=str) + "\n"
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
