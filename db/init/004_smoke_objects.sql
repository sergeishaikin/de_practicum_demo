create table if not exists marts.pipeline_runs (
  run_id varchar primary key,
  run_ts timestamptz not null default now(),
  status varchar not null,
  stg_orders int not null,
  stg_order_items int not null,
  core_order_items int not null,
  mart_sales_days int not null,
  duplicate_grain_rows int not null,
  null_key_rows int not null,
  max_reconcile_diff numeric(12, 2) not null
);

create or replace view marts.v_smoke_last_run as
select
  run_id,
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
