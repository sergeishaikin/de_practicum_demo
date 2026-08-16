select order_id, order_item_id
from {{ ref('v_order_items_wide') }}
group by order_id, order_item_id
having count(*) > 1
