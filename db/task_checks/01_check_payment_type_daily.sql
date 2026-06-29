\set ON_ERROR_STOP on

do $$
declare
  rows_count int;
  null_dates int;
  null_payment_types int;
  sum_diff numeric;
  mismatch_rows int;
begin
  if to_regclass('marts.v_payment_type_daily') is null then
    raise exception 'marts.v_payment_type_daily does not exist';
  end if;

  perform
    sales_date,
    main_payment_type,
    orders_cnt,
    payment_sum,
    avg_payment
  from marts.v_payment_type_daily
  limit 1;

  select count(*)
  into rows_count
  from marts.v_payment_type_daily;

  if rows_count = 0 then
    raise exception 'marts.v_payment_type_daily is empty';
  end if;

  select count(*)
  into null_dates
  from marts.v_payment_type_daily
  where sales_date is null;

  if null_dates > 0 then
    raise exception 'marts.v_payment_type_daily has % rows with null sales_date', null_dates;
  end if;

  select count(*)
  into null_payment_types
  from marts.v_payment_type_daily
  where main_payment_type is null;

  if null_payment_types > 0 then
    raise exception 'marts.v_payment_type_daily has % rows with null main_payment_type', null_payment_types;
  end if;

  select abs(
    coalesce((select sum(payment_sum) from marts.v_payment_type_daily), 0)
    - coalesce((select sum(payment_value) from core.orders), 0)
  )
  into sum_diff;

  if sum_diff > 0.01 then
    raise exception 'payment_sum reconcile diff is %', sum_diff;
  end if;

  with expected as (
    select
      order_purchase_date as sales_date,
      main_payment_type,
      count(*)::int as orders_cnt,
      sum(payment_value)::numeric(12, 2) as payment_sum,
      avg(payment_value)::numeric(12, 2) as avg_payment
    from core.orders
    group by order_purchase_date, main_payment_type
  ),
  compared as (
    select
      coalesce(e.sales_date, v.sales_date) as sales_date,
      coalesce(e.main_payment_type, v.main_payment_type) as main_payment_type,
      e.orders_cnt as expected_orders_cnt,
      v.orders_cnt as actual_orders_cnt,
      e.payment_sum as expected_payment_sum,
      v.payment_sum as actual_payment_sum,
      e.avg_payment as expected_avg_payment,
      v.avg_payment as actual_avg_payment
    from expected e
    full join marts.v_payment_type_daily v
      on v.sales_date = e.sales_date
     and v.main_payment_type = e.main_payment_type
  )
  select count(*)
  into mismatch_rows
  from compared
  where expected_orders_cnt is distinct from actual_orders_cnt
     or expected_payment_sum is distinct from actual_payment_sum
     or expected_avg_payment is distinct from actual_avg_payment;

  if mismatch_rows > 0 then
    raise exception 'marts.v_payment_type_daily has % rows different from expected result', mismatch_rows;
  end if;
end $$;

select
  'sql_task_payment_type_daily' as check_name,
  'ok' as status,
  count(*) as rows_count,
  min(sales_date) as date_from,
  max(sales_date) as date_to,
  sum(payment_sum)::numeric(12, 2) as payment_sum
from marts.v_payment_type_daily;
