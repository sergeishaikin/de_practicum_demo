select
  order_id,
  order_purchase_timestamp,
  ingest_date
from {{ source('staging', 'orders') }}
