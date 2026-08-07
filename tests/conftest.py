import sys
from pathlib import Path

ICEBERG_DIR = Path(__file__).resolve().parents[1] / "iceberg"
if str(ICEBERG_DIR) not in sys.path:
    sys.path.insert(0, str(ICEBERG_DIR))
