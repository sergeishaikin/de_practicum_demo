select order_id
from {{ source('silver', 'orders_clean') }}
group by order_id
having count(*) > 1
