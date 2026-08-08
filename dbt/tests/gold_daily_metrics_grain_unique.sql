select order_date, country, status
from {{ ref('daily_order_metrics') }}
group by order_date, country, status
having count(*) > 1
