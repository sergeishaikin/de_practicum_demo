"""Execute the explicitly approved S1.2B SAFE_STALE manifest cleanup."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ICEBERG_DIR = REPO_ROOT / "iceberg"
if str(ICEBERG_DIR) not in sys.path:
    sys.path.insert(0, str(ICEBERG_DIR))

from medallion.iceberg_medallion import (  # noqa: E402
    get_catalog,
    get_fs,
    list_bronze_work,
    load_progress,
    delete_bronze_work,
)
from medallion.legacy_outbox_reconciliation import (  # noqa: E402
    build_live_receipt,
)

APPROVED_COUNT = 140
APPROVED_DIGEST = (
    "231cefaadc2a0ceb35dfc6a7dacd6f2f75512650d6e1345ead681c84171939bf"
)
OUTBOX_ROOT = "de-practicum/streaming/bronze_outbox/"


def _summary(receipt: dict) -> dict:
    fields = (
        "classified_manifests",
        "safe_stale",
        "live_post_migration",
        "in_flight_blocked",
        "blocked",
        "logical_rows",
        "legacy_null_physical_rows",
        "versioned_physical_rows",
        "bronze_snapshot_id",
        "silver_snapshot_id",
        "bronze_null_business_version_rows",
        "silver_null_business_version_rows",
        "authoritative_bronze_rows",
        "authoritative_silver_rows",
        "silver_unique_order_ids",
        "silver_equals_b2_projection",
        "cleanup_set_digest",
    )
    return {field: receipt.get(field) for field in fields}


def _live_manifest_paths(receipt: dict) -> set[str]:
    return {
        item["manifest"]
        for item in receipt["dispositions"]
        if item["status"] == "LIVE_POST_MIGRATION"
    }


def _pre_delete_gate(receipt: dict, records: list[dict]) -> list[dict]:
    if receipt["in_flight_blocked"] != 0:
        raise RuntimeError("S1.2B gate failed: IN_FLIGHT_BLOCKED is non-zero")
    if receipt["blocked"] != 0:
        raise RuntimeError("S1.2B gate failed: BLOCKED is non-zero")
    if receipt["safe_stale"] != APPROVED_COUNT:
        raise RuntimeError(
            f"S1.2B gate failed: expected {APPROVED_COUNT} SAFE_STALE, "
            f"got {receipt['safe_stale']}"
        )
    if receipt["cleanup_set_digest"] != APPROVED_DIGEST:
        raise RuntimeError(
            "S1.2B gate failed: cleanup digest does not match explicit approval"
        )

    by_path = {
        record["_object_path"]: record
        for record in records
    }
    cleanup_set = receipt["cleanup_set"]
    if len(cleanup_set) != APPROVED_COUNT:
        raise RuntimeError("S1.2B gate failed: cleanup set length mismatch")
    selected = []
    for item in cleanup_set:
        path = item["manifest"]
        if not path.startswith(OUTBOX_ROOT) or not path.endswith(".json"):
            raise RuntimeError(f"S1.2B gate failed: invalid manifest path {path}")
        record = by_path.get(path)
        if record is None or str(record["load_id"]) != str(item["load_id"]):
            raise RuntimeError(f"S1.2B gate failed: manifest identity mismatch {path}")
        selected.append(record)
    if len({record["_object_path"] for record in selected}) != APPROVED_COUNT:
        raise RuntimeError("S1.2B gate failed: cleanup set is not unique")
    return selected


def cleanup(evidence_path: Path) -> dict:
    catalog = get_catalog()
    fs = get_fs()
    progress_before = load_progress(fs)
    records_before = list_bronze_work(fs)
    pre = build_live_receipt(catalog, fs)
    selected = _pre_delete_gate(pre, records_before)
    live_paths_before = _live_manifest_paths(pre)

    deleted = []
    for record in selected:
        delete_bronze_work(fs, record)
        deleted.append(
            {
                "load_id": record["load_id"],
                "manifest": record["_object_path"],
            }
        )

    progress_after = load_progress(fs)
    post = build_live_receipt(catalog, fs)
    live_paths_after = _live_manifest_paths(post)
    post_checks = {
        "safe_stale_zero": post["safe_stale"] == 0,
        "in_flight_blocked_zero": post["in_flight_blocked"] == 0,
        "blocked_zero": post["blocked"] == 0,
        "live_post_migration_preserved": live_paths_after == live_paths_before,
        "bronze_rows_unchanged": (
            post["authoritative_bronze_rows"] == pre["authoritative_bronze_rows"]
        ),
        "silver_rows_unchanged": (
            post["authoritative_silver_rows"] == pre["authoritative_silver_rows"]
        ),
        "bronze_snapshot_unchanged": (
            post["bronze_snapshot_id"] == pre["bronze_snapshot_id"]
        ),
        "silver_snapshot_unchanged": (
            post["silver_snapshot_id"] == pre["silver_snapshot_id"]
        ),
        "bronze_null_versions_zero": post["bronze_null_business_version_rows"] == 0,
        "silver_null_versions_zero": post["silver_null_business_version_rows"] == 0,
        "silver_unique_order_ids": post["silver_unique_order_ids"] is True,
        "silver_equals_b2_projection": post["silver_equals_b2_projection"] is True,
        "progress_unchanged": progress_after == progress_before,
    }
    if not all(post_checks.values()):
        raise RuntimeError(
            f"S1.2B post-cleanup verification failed: {post_checks}"
        )

    receipt = {
        "migration": "S1.2",
        "phase": "S1.2B-cleanup",
        "status": "VERIFIED",
        "approved_count": APPROVED_COUNT,
        "approved_digest": APPROVED_DIGEST,
        "pre_cleanup": _summary(pre),
        "deleted_count": len(deleted),
        "deleted_manifests": deleted,
        "post_cleanup": _summary(post),
        "post_cleanup_checks": post_checks,
        "live_post_migration_count": len(live_paths_after),
        "applied_at": datetime.now(timezone.utc).isoformat(),
    }
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        json.dumps(receipt, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence",
        type=Path,
        default=Path("artifacts/s1.2b-cleanup-receipt.json"),
    )
    args = parser.parse_args()
    print(json.dumps(cleanup(args.evidence), sort_keys=True, indent=2, default=str))


if __name__ == "__main__":
    main()
