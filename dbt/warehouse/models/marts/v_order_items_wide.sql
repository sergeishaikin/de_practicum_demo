{{ config(alias='v_order_items_wide', tags=['contract:mart', 'criticality:tier1']) }}

select
  oi.order_id,
  oi.order_item_id,
  oi.order_purchase_date,
  oi.order_status,
  oi.customer_id,
  oi.customer_state,
  oi.product_id,
  oi.seller_id,
  oi.price,
  oi.freight_value,
  o.payment_value as order_payment_value,
  o.main_payment_type,
  oi.ingest_date
from {{ source('core', 'order_items') }} oi
left join {{ source('core', 'orders') }} o
  on o.order_id = oi.order_id
