-- Property test: the wide view is a LEFT JOIN from core.order_items onto a
-- unique order key, so it must neither drop nor multiply item rows.
--
-- This is a different failure mode from the grain test. composite_unique on
-- (order_id, order_item_id) catches fan-out that produces *duplicate keys*; it
-- cannot see rows that were silently dropped by an inner join, nor a fan-out
-- that somehow preserved key uniqueness. A count comparison catches both
-- directions, and names which one occurred.

with wide as (
  select count(*) as n from {{ ref('v_order_items_wide') }}
), core_items as (
  select count(*) as n from {{ source('core', 'order_items') }}
)
select
  core_items.n as core_order_items_rows,
  wide.n as wide_rows,
  case
    when wide.n > core_items.n then 'fan-out: join multiplied rows'
    else 'row loss: join dropped items'
  end as failure_mode
from wide cross join core_items
where wide.n <> core_items.n
