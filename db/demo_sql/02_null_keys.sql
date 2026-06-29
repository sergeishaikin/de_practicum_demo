select
  'marts.v_order_items_wide null grain keys' as check_name,
  count(*) as failed_rows
from marts.v_order_items_wide
where order_id is null
   or order_item_id is null
union all
select
  'marts.v_order_items_wide null business keys' as check_name,
  count(*) as failed_rows
from marts.v_order_items_wide
where customer_id is null
   or product_id is null
   or seller_id is null;
