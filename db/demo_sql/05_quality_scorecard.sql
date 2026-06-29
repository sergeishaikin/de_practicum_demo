with checks as (
  select
    'stg.orders loaded' as check_name,
    count(*)::numeric as metric_value,
    case when count(*) > 0 then 'ok' else 'fail' end as status
  from stg.orders
  union all
  select
    'stg.order_items loaded',
    count(*)::numeric,
    case when count(*) > 0 then 'ok' else 'fail' end
  from stg.order_items
  union all
  select
    'core.order_items matches stg.order_items',
    (
      (select count(*) from core.order_items)
      - (select count(*) from stg.order_items)
    )::numeric,
    case
      when (select count(*) from core.order_items) = (select count(*) from stg.order_items)
      then 'ok'
      else 'fail'
    end
  union all
  select
    'duplicate grain rows',
    count(*)::numeric,
    case when count(*) = 0 then 'ok' else 'fail' end
  from (
    select order_id, order_item_id
    from marts.v_order_items_wide
    group by order_id, order_item_id
    having count(*) > 1
  ) d
  union all
  select
    'null business keys',
    count(*)::numeric,
    case when count(*) = 0 then 'ok' else 'fail' end
  from marts.v_order_items_wide
  where order_id is null
     or order_item_id is null
     or customer_id is null
     or product_id is null
     or seller_id is null
  union all
  select
    'max reconcile diff',
    coalesce(max(abs(diff_amount)), 0)::numeric,
    case
      when coalesce(max(abs(diff_amount)), 0) <= 0.01 then 'ok'
      else 'fail'
    end
  from marts.v_reconcile_sales_daily
)
select
  check_name,
  metric_value,
  status
from checks
order by
  case status when 'fail' then 1 else 2 end,
  check_name;
