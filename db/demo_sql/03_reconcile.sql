select
  sales_date,
  mart_gross_sales,
  source_gross_sales,
  diff_amount
from marts.v_reconcile_sales_daily
where abs(diff_amount) > 0.01
order by sales_date;

select
  'max_abs_reconcile_diff' as metric_name,
  coalesce(max(abs(diff_amount)), 0)::numeric(12, 2) as metric_value
from marts.v_reconcile_sales_daily;
