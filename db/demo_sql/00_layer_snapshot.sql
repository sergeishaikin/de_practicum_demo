with layer_snapshot as (
  select
    'stg' as layer_name,
    'orders' as object_name,
    min(order_purchase_timestamp::date) as date_from,
    max(order_purchase_timestamp::date) as date_to,
    count(*) as rows_count
  from stg.orders
  union all
  select
    'stg',
    'order_items',
    min(o.order_purchase_timestamp::date),
    max(o.order_purchase_timestamp::date),
    count(oi.*)
  from stg.order_items oi
  left join stg.orders o
    on o.order_id = oi.order_id
   and o.ingest_date = oi.ingest_date
  union all
  select
    'core',
    'orders',
    min(order_purchase_date),
    max(order_purchase_date),
    count(*)
  from core.orders
  union all
  select
    'core',
    'order_items',
    min(order_purchase_date),
    max(order_purchase_date),
    count(*)
  from core.order_items
  union all
  select
    'staging',
    'stg_core__order_items',
    min(order_purchase_date),
    max(order_purchase_date),
    count(*)
  from staging.stg_core__order_items
  union all
  select
    'staging',
    'stg_staging__order_items',
    null::date,
    null::date,
    count(*)
  from staging.stg_staging__order_items
  union all
  select
    'marts',
    'v_sales_daily',
    min(sales_date),
    max(sales_date),
    count(*)
  from marts.v_sales_daily
  union all
  select
    'marts',
    'v_customer_state_daily',
    min(sales_date),
    max(sales_date),
    count(*)
  from marts.v_customer_state_daily
)
select
  layer_name,
  object_name,
  coalesce(date_from::text, 'no data') as date_from,
  coalesce(date_to::text, 'no data') as date_to,
  rows_count
from layer_snapshot
order by
  case layer_name
    when 'stg' then 1
    when 'core' then 2
    when 'staging' then 3
    when 'marts' then 4
  end,
  object_name;
