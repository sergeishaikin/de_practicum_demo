select
  order_id,
  customer_id,
  customer_state,
  order_status,
  order_purchase_date,
  payment_value,
  main_payment_type,
  max_installments,
  ingest_date
from {{ source('core', 'orders') }}
