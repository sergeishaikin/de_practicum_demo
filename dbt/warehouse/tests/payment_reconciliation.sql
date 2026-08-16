with source_payments as (
  select coalesce(sum(payment_value), 0)::numeric(12, 2) as total
  from {{ source('staging', 'order_payments') }}
), core_orders as (
  select coalesce(sum(payment_value), 0)::numeric(12, 2) as total
  from {{ source('core', 'orders') }}
)
select
  source_payments.total as staging_payment_total,
  core_orders.total as core_payment_total,
  (source_payments.total - core_orders.total)::numeric(12, 2) as diff_amount
from source_payments cross join core_orders
where abs(source_payments.total - core_orders.total) > 0.01
