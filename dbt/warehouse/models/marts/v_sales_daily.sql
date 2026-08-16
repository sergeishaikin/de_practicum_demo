{{ config(alias='v_sales_daily', tags=['contract:mart', 'criticality:tier1']) }}

select
  order_purchase_date as sales_date,
  count(distinct order_id) as orders_cnt,
  count(*) as items_cnt,
  sum(price)::numeric(12, 2) as gross_sales,
  sum(freight_value)::numeric(12, 2) as freight_sum
from {{ source('core', 'order_items') }}
group by order_purchase_date
