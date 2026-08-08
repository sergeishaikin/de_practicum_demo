# SPIKE-2 — PyIceberg B2 physical layout

Status: live measurement complete; D-3 accepted; D-3a physical layout tuning deferred.

## Question

Can the PyIceberg-owned business-key projection preserve D-1 while keeping the
physical cost acceptable for a small update set?

The harness compares:

- B2a: `day(event_date)`;
- B2b: `bucket(order_id, N)` (default `N=16`).

Both variants use the same operation:

1. collapse the incoming batch to the greatest `business_version` per
   `order_id`;
2. reject FF-14 equal-version payload conflicts;
3. read current Silver rows for affected keys;
4. resolve the greatest version;
5. call `overwrite(overwrite_filter=order_id IN (...))` only for advancing keys.

## Gates and measurements

The integration test checks global uniqueness, monotonic versions, a
cross-date update, source pre-collapse, replay, and lower-version no-op
behaviour. FF-14 is also covered without a live catalog in
`tests/test_b2_spike.py`.

Each layout prints JSON containing:

```text
files_planned_for_read
bytes_planned_for_read
data_files_removed
data_files_added
bytes_removed
bytes_added
snapshot_count_delta
```

The default fixture has 10 days, 1,000 orders per day, and four seed appends
per day. It is intentionally configurable:

```powershell
$env:B2_SPIKE_DAYS = "10"
$env:B2_SPIKE_ORDERS_PER_DAY = "1000"
$env:B2_SPIKE_CHUNKS_PER_DAY = "4"
$env:B2_SPIKE_BUCKET_COUNT = "16"
python -m pytest -m spike2 tests/integration/test_b2_pyiceberg_layout.py -s
```

The result is the baseline evidence for ADR-0001 D-3a. It does not define a
correctness threshold and must not block the accepted B2 execution model. This
spike does not implement the production medallion path or the D-2
control/outbox boundary.

## Live result — 2026-08-08

Run parameters: 10 days, 10,000 seeded orders, 4 appends per day, 16 buckets,
10 update keys. Both variants passed G1, G2, G3, G4, G5, and G6. The live
test completed with `1 passed`.

| Metric | B2a `day(event_date)` | B2b `bucket(order_id,16)` |
|---|---:|---:|
| Initial data files | 40 | 640 |
| Initial data bytes | 172,697 | 2,000,698 |
| Planned files read | 10 (25.00%) | 27 (4.22%) |
| Planned bytes read | 43,420 (25.14%) | 84,831 (4.24%) |
| Data files removed | 10 (25.00%) | 10 (1.56%) |
| Bytes removed | 43,420 (25.14%) | 31,572 (1.58%) |
| Data files added | 11 | 18 |
| Bytes added | 46,864 | 54,928 |
| Snapshot delta | 2 | 2 |
| G1 uniqueness | PASS | PASS |
| G3 cross-day update | PASS | PASS |
| Replay idempotency | PASS | PASS |

Interpretation: B2b localizes the changed fraction of the much larger
partitioned table, but its default fixture creates 16x as many small files.
Consequently B2b reads more absolute bytes and adds more files than B2a for
this 10-key update, despite its much smaller percentage of Silver touched.
The result is evidence for a layout trade-off, not yet a production choice;
the next comparison should control target file size/compaction before D-3 is
closed.
