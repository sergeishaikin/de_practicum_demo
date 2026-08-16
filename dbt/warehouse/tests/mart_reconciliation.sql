select sales_date, diff_amount
from {{ ref('v_reconcile_sales_daily') }}
where abs(diff_amount) > 0.01
