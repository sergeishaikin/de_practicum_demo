"""Read-only S1.2A reconciliation for legacy Bronze outbox manifests.

The classifier proves that an old outbox manifest is stale only when all of
the following are true:

* its load-id is represented by a pre-migration Bronze snapshot;
* its physical rows are present in the migrated authoritative Bronze image;
* the current Silver image contains the corresponding B2 current state; and
* no active medallion progress entry still depends on the manifest.

This module deliberately has no cleanup operation.  The only live operation
is a read-only dry run which emits a receipt suitable for a separately
approved cleanup step.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

import pyarrow as pa
from pyiceberg.expressions import In

REPO_ICEBERG_DIR = Path(__file__).resolve().parents[1]
if str(REPO_ICEBERG_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_ICEBERG_DIR))

from medallion.iceberg_medallion import (  # noqa: E402
    BRONZE_NAMESPACE,
    BRONZE_TABLE,
    SILVER_NAMESPACE,
    SILVER_TABLE,
    get_catalog,
    get_fs,
    list_bronze_work,
    load_progress,
    read_bronze_work,
    _mark_b2_completed,
)
from medallion.legacy_business_version_migration import (  # noqa: E402
    LEGACY_VERSION,
    MIGRATION_MARKER,
    _same_rows,
    b2_projection,
)
from b2_spike import resolve_against_current  # noqa: E402

MIGRATION_NAME = "S1.2"
SCHEMA_VERSION = 1


def _canonical_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    return value


def _canonical_row(row: dict, *, normalize_legacy: bool = False) -> tuple:
    values = []
    for name, value in sorted(row.items()):
        if normalize_legacy and name == "business_version" and value is None:
            value = LEGACY_VERSION
        values.append((name, _canonical_value(value)))
    if normalize_legacy and "business_version" not in row:
        values.append(("business_version", LEGACY_VERSION))
    return tuple(values)


def _payload_key(row: dict) -> tuple:
    return tuple(
        (name, _canonical_value(value))
        for name, value in sorted(row.items())
        if name != "business_version"
    )


def _row_id(row: dict) -> str | None:
    value = row.get("order_id")
    return None if value is None else str(value)


@dataclass(frozen=True)
class SnapshotEvidence:
    snapshot_id: int | str
    timestamp_ms: int
    load_id: str | None
    migration_marker: str | None

    @property
    def timestamp_iso(self) -> str:
        return datetime.fromtimestamp(
            self.timestamp_ms / 1000, tz=timezone.utc
        ).isoformat()


def snapshot_evidence(table) -> list[SnapshotEvidence]:
    evidence = []
    for snapshot in table.metadata.snapshots:
        summary = snapshot.summary.additional_properties if snapshot.summary else {}
        evidence.append(
            SnapshotEvidence(
                snapshot_id=snapshot.snapshot_id,
                timestamp_ms=int(snapshot.timestamp_ms),
                load_id=summary.get("load-id"),
                migration_marker=summary.get("business-version-migration"),
            )
        )
    return evidence


def migration_boundary(snapshots: Iterable[SnapshotEvidence]) -> SnapshotEvidence | None:
    markers = [
        item
        for item in snapshots
        if item.migration_marker == MIGRATION_MARKER
    ]
    return max(markers, key=lambda item: (item.timestamp_ms, str(item.snapshot_id))) if markers else None


def _progress_references(record: dict, progress: dict) -> list[str]:
    record_load_id = str(record["load_id"])
    record_files = set(record.get("bronze_data_files", []))
    record_sources = set(record.get("source_paths", []))
    matches = []
    for load_id, work in progress.get("work", {}).items():
        work_files = set(work.get("bronze_data_files", []))
        work_sources = set(work.get("source_paths", []))
        if (
            str(load_id) == record_load_id
            or record_files & work_files
            or record_sources & work_sources
        ):
            matches.append(str(load_id))
    return sorted(set(matches))


def _reason_counts(dispositions: Iterable[dict]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in dispositions:
        counts.update(item["blocked_reasons"])
    return dict(sorted(counts.items()))


def cleanup_set_digest(cleanup_set: Iterable[dict]) -> str:
    canonical = [
        {
            "load_id": str(item["load_id"]),
            "manifest": item["manifest"],
        }
        for item in cleanup_set
    ]
    payload = json.dumps(
        sorted(canonical, key=lambda item: (item["load_id"], item["manifest"])),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def classify_manifests(
    manifests: list[dict],
    rows_by_load_id: dict[str, list[dict]],
    authoritative_bronze_rows: list[dict],
    silver_rows: list[dict],
    snapshots_by_load_id: dict[str, list[SnapshotEvidence]],
    migration_boundary_evidence: SnapshotEvidence | None,
    progress: dict,
) -> dict:
    """Classify manifests using only supplied read-only evidence.

    The authoritative row counter is consumed once across the complete
    manifest set.  This is important: it proves that the proposed cleanup set
    does not contain duplicate logical work hidden behind repeated manifests.
    """

    available_rows: Counter = Counter(
        _canonical_row(row, normalize_legacy=False)
        for row in authoritative_bronze_rows
    )
    silver_by_id = {str(row["order_id"]): row for row in silver_rows}
    authoritative_by_id = {
        str(row["order_id"]): row for row in authoritative_bronze_rows
    }
    dispositions: list[dict] = []

    for manifest in sorted(manifests, key=lambda item: str(item["load_id"])):
        load_id = str(manifest["load_id"])
        reasons: list[str] = []
        rows = rows_by_load_id.get(load_id, [])

        if not manifest.get("bronze_data_files"):
            reasons.append("no_physical_file_provenance")

        matching_snapshots = snapshots_by_load_id.get(load_id, [])
        if not matching_snapshots:
            reasons.append("load_id_not_found_in_bronze_snapshot_history")
        elif len(matching_snapshots) != 1:
            reasons.append("load_id_has_ambiguous_bronze_snapshots")
        elif (
            migration_boundary_evidence is None
            or matching_snapshots[0].timestamp_ms
            > migration_boundary_evidence.timestamp_ms
        ):
            reasons.append("manifest_is_post_migration_work")

        active_refs = _progress_references(manifest, progress)
        if active_refs:
            reasons.append("active_or_inflight_progress")

        local_unmatched = 0
        null_rows = 0
        versioned_rows = 0
        manifest_order_ids: set[str] = set()
        for row in rows:
            order_id = _row_id(row)
            if order_id is None:
                reasons.append("null_order_id")
                continue
            manifest_order_ids.add(order_id)
            if row.get("business_version") is None:
                null_rows += 1
                key = _canonical_row(row, normalize_legacy=True)
            else:
                versioned_rows += 1
                key = _canonical_row(row)
            if available_rows[key] <= 0:
                local_unmatched += 1
            else:
                available_rows[key] -= 1

        if local_unmatched:
            reasons.append("rows_not_fully_represented_in_authoritative_bronze")

        for order_id in sorted(manifest_order_ids):
            authoritative = authoritative_by_id.get(order_id)
            silver = silver_by_id.get(order_id)
            if authoritative is None:
                reasons.append("order_id_missing_from_authoritative_bronze")
            elif silver is None:
                reasons.append("order_id_missing_from_current_silver")
            elif silver.get("business_version") != authoritative.get("business_version"):
                reasons.append("silver_not_at_authoritative_b2_version")

        post_migration = "manifest_is_post_migration_work" in reasons
        active = bool(active_refs)
        if active:
            status = "IN_FLIGHT_BLOCKED"
        elif post_migration and set(reasons) == {"manifest_is_post_migration_work"}:
            status = "LIVE_POST_MIGRATION"
        elif not reasons:
            status = "SAFE_STALE"
        else:
            status = "BLOCKED"
        blocking_reasons = (
            sorted(set(reasons))
            if status in {"IN_FLIGHT_BLOCKED", "BLOCKED"}
            else []
        )

        dispositions.append(
            {
                "load_id": load_id,
                "manifest": manifest.get("_object_path"),
                "bronze_data_files": sorted(manifest.get("bronze_data_files", [])),
                "source_paths": sorted(manifest.get("source_paths", [])),
                "logical_rows": len(rows),
                "legacy_null_physical_rows": null_rows,
                "versioned_physical_rows": versioned_rows,
                "active_progress_refs": active_refs,
                "disposition_reasons": sorted(set(reasons)),
                "blocked_reasons": blocking_reasons,
                "status": status,
            }
        )

    safe = [
        {"load_id": item["load_id"], "manifest": item["manifest"]}
        for item in dispositions
        if item["status"] == "SAFE_STALE"
    ]
    live = [
        item for item in dispositions if item["status"] == "LIVE_POST_MIGRATION"
    ]
    inflight = [
        item for item in dispositions if item["status"] == "IN_FLIGHT_BLOCKED"
    ]
    blocked = [item for item in dispositions if item["status"] == "BLOCKED"]
    return {
        "classified_manifests": len(dispositions),
        "safe_stale": len(safe),
        "live_post_migration": len(live),
        "in_flight_blocked": len(inflight),
        "blocked": len(blocked),
        "logical_rows": sum(item["logical_rows"] for item in dispositions),
        "legacy_null_physical_rows": sum(
            item["legacy_null_physical_rows"] for item in dispositions
        ),
        "versioned_physical_rows": sum(
            item["versioned_physical_rows"] for item in dispositions
        ),
        "cleanup_set": safe,
        "cleanup_set_digest": cleanup_set_digest(safe),
        "blocked_reasons": _reason_counts(dispositions),
        "dispositions": dispositions,
    }


def _table_rows(table) -> list[dict]:
    return table.scan().to_arrow().to_pylist()


def reconcile_inflight_noop(catalog, fs, load_id: str) -> dict:
    """Acknowledge an already-materialized no-op without deleting its manifest.

    This is the S1.2A.1 recovery seam.  It uses the same M3 durable progress
    commit helper as normal B2 processing, but intentionally leaves the
    outbox object for the separately approved S1.2B cleanup.  It fails closed
    unless the raw legacy rows normalize to the authoritative Bronze image
    and ``resolve_against_current`` proves that Silver needs no mutation.
    """

    bronze = catalog.load_table(f"{BRONZE_NAMESPACE}.{BRONZE_TABLE}")
    silver = catalog.load_table(f"{SILVER_NAMESPACE}.{SILVER_TABLE}")
    progress = load_progress(fs)
    manifests = list_bronze_work(fs)
    record = next((item for item in manifests if item["load_id"] == load_id), None)
    if record is None:
        raise RuntimeError(f"S1.2A.1 manifest not found: {load_id}")
    work = progress.get("work", {}).get(load_id)
    if work is None:
        raise RuntimeError(f"S1.2A.1 work is not in-flight: {load_id}")
    if load_id in progress.get("completed", {}):
        raise RuntimeError(f"S1.2A.1 work is already completed: {load_id}")

    work_snapshots = []
    for snapshot in silver.metadata.snapshots:
        summary = snapshot.summary.additional_properties if snapshot.summary else {}
        if summary.get("silver-work-id") == load_id:
            work_snapshots.append(snapshot.snapshot_id)
    if work_snapshots:
        raise RuntimeError(
            "S1.2A.1 requires the normal committed-snapshot recovery path; "
            f"found Silver work snapshots {work_snapshots} for {load_id}"
        )

    raw_rows = read_bronze_work(fs, bronze, record).to_pylist()
    authoritative_rows = _table_rows(bronze)
    authoritative_keys = Counter(
        _canonical_row(row) for row in authoritative_rows
    )
    normalized_rows = []
    for row in raw_rows:
        normalized = dict(row)
        if normalized.get("business_version") is None:
            normalized["business_version"] = LEGACY_VERSION
        key = _canonical_row(normalized)
        if authoritative_keys[key] <= 0:
            raise RuntimeError(
                "S1.2A.1 raw work row is not represented in authoritative Bronze"
            )
        authoritative_keys[key] -= 1
        normalized_rows.append(normalized)

    current_ids = sorted({str(row["order_id"]) for row in normalized_rows})
    current = silver.scan(row_filter=In("order_id", current_ids)).to_arrow().to_pylist()
    resolved = resolve_against_current(current, normalized_rows)
    if resolved:
        raise RuntimeError(
            "S1.2A.1 is not a no-op; normal B2 retry is required for advancing keys"
        )

    _mark_b2_completed(
        fs,
        progress,
        record,
        snapshot_id=None,
        changed_keys=[],
        delete_outbox=False,
    )
    return {
        "load_id": load_id,
        "raw_rows": len(raw_rows),
        "normalized_legacy_rows": sum(
            row.get("business_version") == LEGACY_VERSION
            and raw.get("business_version") is None
            for raw, row in zip(raw_rows, normalized_rows, strict=True)
        ),
        "resolved_rows": len(resolved),
        "silver_snapshot_id": silver.current_snapshot().snapshot_id
        if silver.current_snapshot()
        else None,
        "progress_completed": True,
        "manifest_deleted": False,
    }


def build_live_receipt(catalog, fs) -> dict:
    bronze = catalog.load_table(f"{BRONZE_NAMESPACE}.{BRONZE_TABLE}")
    silver = catalog.load_table(f"{SILVER_NAMESPACE}.{SILVER_TABLE}")
    bronze_rows = _table_rows(bronze)
    silver_rows = _table_rows(silver)
    expected_silver = b2_projection(pa.Table.from_pylist(bronze_rows))
    migration_snapshots = snapshot_evidence(bronze)
    boundary = migration_boundary(migration_snapshots)
    snapshots_by_load_id: defaultdict[str, list[SnapshotEvidence]] = defaultdict(list)
    for item in migration_snapshots:
        if item.load_id:
            snapshots_by_load_id[str(item.load_id)].append(item)

    manifests = list_bronze_work(fs)
    rows_by_load_id: dict[str, list[dict]] = {}
    for manifest in manifests:
        load_id = str(manifest["load_id"])
        if manifest.get("bronze_data_files"):
            rows_by_load_id[load_id] = read_bronze_work(fs, bronze, manifest).to_pylist()
        else:
            rows_by_load_id[load_id] = []

    progress = load_progress(fs)
    result = classify_manifests(
        manifests,
        rows_by_load_id,
        bronze_rows,
        silver_rows,
        dict(snapshots_by_load_id),
        boundary,
        progress,
    )
    null_bronze_rows = sum(
        row.get("business_version") is None for row in bronze_rows
    )
    result.update(
        {
            "migration": MIGRATION_NAME,
            "phase": "dry-run",
            "schema_version": SCHEMA_VERSION,
            "bronze_snapshot_id": (
                bronze.current_snapshot().snapshot_id
                if bronze.current_snapshot()
                else None
            ),
            "silver_snapshot_id": (
                silver.current_snapshot().snapshot_id
                if silver.current_snapshot()
                else None
            ),
            "migration_snapshot_id": boundary.snapshot_id if boundary else None,
            "migration_boundary": boundary.timestamp_iso if boundary else None,
            "migration_boundary_timestamp_ms": (
                boundary.timestamp_ms if boundary else None
            ),
            "bronze_null_business_version_rows": null_bronze_rows,
            "authoritative_bronze_rows": len(bronze_rows),
            "authoritative_silver_rows": len(silver_rows),
            "silver_equals_b2_projection": _same_rows(
                silver.scan().to_arrow(), expected_silver
            ),
            "inflight_progress_count": len(progress.get("work", {})),
            "inflight_progress_load_ids": sorted(
                str(load_id) for load_id in progress.get("work", {})
            ),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence",
        type=Path,
        help="write the read-only receipt to this local path",
    )
    args = parser.parse_args()
    receipt = build_live_receipt(get_catalog(), get_fs())
    payload = json.dumps(receipt, sort_keys=True, indent=2, default=str) + "\n"
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
