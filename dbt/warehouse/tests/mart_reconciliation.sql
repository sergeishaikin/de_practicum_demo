-- Tier-1: persist violating rows so a failure names the day and the amount.
{{ config(store_failures=true) }}

select sales_date, diff_amount
from {{ ref('v_reconcile_sales_daily') }}
where abs(diff_amount) > 0.01
