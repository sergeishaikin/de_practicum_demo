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
limit 5;

select *
from marts.v_smoke_last_run;
