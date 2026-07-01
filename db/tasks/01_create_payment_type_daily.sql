-- Задание 1: создай marts.v_payment_type_daily.
--
-- Отредактируй этот файл, затем запусти проверку:
-- scripts\check_task_sql.cmd
--
-- Обязательные колонки:
--   sales_date
--   main_payment_type
--   orders_cnt
--   payment_sum
--   avg_payment
--
-- Таблица-источник:
--   core.orders

create or replace view marts.v_payment_type_daily as
select
  null::date as sales_date,
  null::varchar as main_payment_type,
  0::int as orders_cnt,
  0::numeric(12, 2) as payment_sum,
  0::numeric(12, 2) as avg_payment
where false;
