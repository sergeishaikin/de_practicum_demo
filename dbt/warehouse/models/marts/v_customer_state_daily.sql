{{ config(alias='v_customer_state_daily', tags=['contract:mart', 'criticality:tier2']) }}

select
  order_purchase_date as sales_date,
  customer_state,
  count(distinct order_id) as orders_cnt,
  count(*) as items_cnt,
  sum(price)::numeric(12, 2) as gross_sales
from {{ source('core', 'order_items') }}
group by order_purchase_date, customer_state
