select
  order_id,
  order_item_id,
  order_purchase_date,
  order_status,
  customer_id,
  customer_state,
  product_id,
  seller_id,
  price,
  freight_value,
  ingest_date
from {{ source('core', 'order_items') }}
