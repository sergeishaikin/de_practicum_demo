-- Tier-1: persist violating rows so a failure names the order and the mode.
{{ config(store_failures=true) }}

-- Staging-to-core payment reconciliation at the *order* grain.
--
-- This deliberately replaces a single global SUM comparison. A global total
-- passes whenever errors cancel out:
--
--   order A: source 100, core  90   -10
--   order B: source 100, core 110   +10
--   ------------------------------------
--   total:   source 200, core 200   PASS
--
-- Reconciling per (order_id, ingest_date) - the exact grain the payment
-- aggregation in db/pipeline_sql/10_rebuild_core.sql groups by - makes those
-- two rows two failures instead of one false pass, and names which orders.
--
-- A FULL JOIN is used so that a payment set with no core order, and a core order
-- whose payments vanished, are both reported rather than silently skipped.

with source_payments as (
  select
    order_id,
    ingest_date,
    sum(payment_value)::numeric(12, 2) as source_total
  from {{ source('staging', 'order_payments') }}
  group by order_id, ingest_date
), core_payments as (
  select
    order_id,
    ingest_date,
    coalesce(payment_value, 0)::numeric(12, 2) as core_total
  from {{ source('core', 'orders') }}
)
select
  coalesce(s.order_id, c.order_id) as order_id,
  coalesce(s.ingest_date, c.ingest_date) as ingest_date,
  coalesce(s.source_total, 0) as source_total,
  coalesce(c.core_total, 0) as core_total,
  (coalesce(s.source_total, 0) - coalesce(c.core_total, 0))::numeric(12, 2) as diff_amount,
  case
    when s.order_id is null then 'core order has no staging payments'
    when c.order_id is null then 'staging payments have no core order'
    else 'amount mismatch'
  end as failure_mode
from source_payments s
full join core_payments c
  on c.order_id = s.order_id
 and c.ingest_date = s.ingest_date
where abs(coalesce(s.source_total, 0) - coalesce(c.core_total, 0)) > 0.01
