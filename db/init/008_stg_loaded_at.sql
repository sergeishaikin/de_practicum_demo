-- Batch-load transaction timestamp for the four staging tables.
--
-- This records *when the load transaction started*, not literal row-arrival
-- time. `now()` is transaction-start time and is constant for the whole
-- transaction, and `load_raw_csv_to_stg` wraps the truncate plus all four COPY
-- calls in a single `with _connect() as conn:` block. One batch therefore
-- yields one identical `loaded_at` across all four tables, by construction
-- rather than by coincidence, so the four sources can never report
-- inconsistent freshness. `clock_timestamp()` would vary per row and break
-- that invariant; it is deliberately not used.
--
-- `loaded_at` is deliberately absent from every CSV and from every COPY column
-- list in `dags/warehouse_orders.py`, so PostgreSQL supplies the default on
-- every load. The ingestion DAG needs no change for this column to populate.
--
-- Accepted false-fresh window: `add column ... not null default now()` assigns
-- the evaluated default to pre-existing rows too, so immediately after this
-- migration old staging rows report as freshly loaded. That is accepted, not
-- fixed. The window is one ingestion run wide, the freshness gate is only ever
-- reached after `load_raw_csv_to_stg` has truncated those rows, and the failure
-- mode is a false pass rather than a false failure. A nullable transitional
-- column or a sentinel timestamp would add permanent schema complexity to guard
-- a one-time state, and is explicitly rejected.

alter table if exists stg.orders
  add column if not exists loaded_at timestamptz not null default now();

alter table if exists stg.order_items
  add column if not exists loaded_at timestamptz not null default now();

alter table if exists stg.order_payments
  add column if not exists loaded_at timestamptz not null default now();

alter table if exists stg.customers
  add column if not exists loaded_at timestamptz not null default now();
