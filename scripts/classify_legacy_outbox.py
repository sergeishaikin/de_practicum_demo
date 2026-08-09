"""Run the S1.2A read-only legacy outbox classifier."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ICEBERG_DIR = REPO_ROOT / "iceberg"
if str(ICEBERG_DIR) not in sys.path:
    sys.path.insert(0, str(ICEBERG_DIR))

from medallion.legacy_outbox_reconciliation import main  # noqa: E402


if __name__ == "__main__":
    main()
