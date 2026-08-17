-- Property test: a day can never contain more distinct orders than line items,
-- because every order contributes at least one item to the grain it is counted
-- from. A violation means COUNT(DISTINCT order_id) and COUNT(*) have been
-- swapped, or the model is aggregating a different grain than it claims.

select
  sales_date,
  orders_cnt,
  items_cnt
from {{ ref('v_sales_daily') }}
where orders_cnt > items_cnt
