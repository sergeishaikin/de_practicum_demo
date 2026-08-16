alter table if exists marts.pipeline_runs
  add column if not exists ingestion_run_id varchar;

create index if not exists idx_pipeline_runs_ingestion_run_id
  on marts.pipeline_runs (ingestion_run_id);

create or replace view marts.v_smoke_last_run as
select
  run_id,
  ingestion_run_id,
  run_ts,
  status,
  stg_orders,
  stg_order_items,
  core_order_items,
  mart_sales_days,
  duplicate_grain_rows,
  null_key_rows,
  max_reconcile_diff
from marts.pipeline_runs
order by run_ts desc
limit 1;
