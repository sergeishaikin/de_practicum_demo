-- Tier-1: persist violating rows so a failure names the duplicated grain keys.
{{ config(store_failures=true) }}

select order_id, order_item_id
from {{ ref('v_order_items_wide') }}
group by order_id, order_item_id
having count(*) > 1
