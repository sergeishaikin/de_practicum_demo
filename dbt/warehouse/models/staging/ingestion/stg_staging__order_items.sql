select
  order_id,
  order_item_id,
  price,
  ingest_date
from {{ source('staging', 'order_items') }}
