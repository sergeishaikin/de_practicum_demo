-- Task 1: create marts.v_payment_type_daily.
--
-- Edit this file, then run:
-- scripts\check_task_sql.cmd
--
-- Required columns:
--   sales_date
--   main_payment_type
--   orders_cnt
--   payment_sum
--   avg_payment
--
-- Source table:
--   core.orders

create or replace view marts.v_payment_type_daily as
select
  null::date as sales_date,
  null::varchar as main_payment_type,
  0::int as orders_cnt,
  0::numeric(12, 2) as payment_sum,
  0::numeric(12, 2) as avg_payment
where false;
