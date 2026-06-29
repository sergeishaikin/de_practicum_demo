select
  'marts.v_order_items_wide duplicate (order_id, order_item_id)' as check_name,
  count(*) as failed_rows
from (
  select order_id, order_item_id
  from marts.v_order_items_wide
  group by order_id, order_item_id
  having count(*) > 1
) d
union all
select
  'core.orders duplicate order_id' as check_name,
  count(*) as failed_rows
from (
  select order_id
  from core.orders
  group by order_id
  having count(*) > 1
) d;
