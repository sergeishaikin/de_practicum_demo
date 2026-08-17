-- Expectations for the staging -> core -> marts -> reconciliation integration
-- check. Run after tests/fixtures/warehouse/seed_staging.sql,
-- db/pipeline_sql/10_rebuild_core.sql and `dbt build` on dbt/warehouse.
--
-- Contract: this query must return ZERO rows. Every returned row is a failure
-- naming the relation, the kind of divergence, and the offending tuple.

with expected_core_orders(order_id, customer_state, order_purchase_date, payment_value, main_payment_type, max_installments) as (
  values
    ('ord-1', 'BE', date '2026-02-01',  55.00::numeric(12, 2), 'credit_card', 3),
    ('ord-2', 'NL', date '2026-02-01', 105.00::numeric(12, 2), 'boleto',      1),
    ('ord-3', 'BE', date '2026-02-02', 210.00::numeric(12, 2), 'credit_card', 1)
), actual_core_orders as (
  select
    order_id,
    customer_state,
    order_purchase_date,
    payment_value::numeric(12, 2),
    main_payment_type,
    max_installments
  from core.orders
), expected_sales_daily(sales_date, orders_cnt, items_cnt, gross_sales, freight_sum) as (
  values
    (date '2026-02-01', 2::bigint, 3::bigint, 150.00::numeric(12, 2), 10.00::numeric(12, 2)),
    (date '2026-02-02', 1::bigint, 1::bigint, 200.00::numeric(12, 2), 10.00::numeric(12, 2))
), actual_sales_daily as (
  select
    sales_date,
    orders_cnt::bigint,
    items_cnt::bigint,
    gross_sales::numeric(12, 2),
    freight_sum::numeric(12, 2)
  from marts.v_sales_daily
), expected_state_daily(sales_date, customer_state, orders_cnt, items_cnt, gross_sales) as (
  values
    (date '2026-02-01', 'BE', 1::bigint, 2::bigint,  50.00::numeric(12, 2)),
    (date '2026-02-01', 'NL', 1::bigint, 1::bigint, 100.00::numeric(12, 2)),
    (date '2026-02-02', 'BE', 1::bigint, 1::bigint, 200.00::numeric(12, 2))
), actual_state_daily as (
  select
    sales_date,
    customer_state,
    orders_cnt::bigint,
    items_cnt::bigint,
    gross_sales::numeric(12, 2)
  from marts.v_customer_state_daily
), expected_items_wide(order_id, order_item_id, customer_state, price, order_payment_value, main_payment_type) as (
  values
    ('ord-1', 1, 'BE',  20.00::numeric(12, 2),  55.00::numeric(12, 2), 'credit_card'),
    ('ord-1', 2, 'BE',  30.00::numeric(12, 2),  55.00::numeric(12, 2), 'credit_card'),
    ('ord-2', 1, 'NL', 100.00::numeric(12, 2), 105.00::numeric(12, 2), 'boleto'),
    ('ord-3', 1, 'BE', 200.00::numeric(12, 2), 210.00::numeric(12, 2), 'credit_card')
), actual_items_wide as (
  select
    order_id,
    order_item_id,
    customer_state,
    price::numeric(12, 2),
    order_payment_value::numeric(12, 2),
    main_payment_type
  from marts.v_order_items_wide
), expected_reconcile(sales_date, mart_gross_sales, source_gross_sales, diff_amount) as (
  values
    (date '2026-02-01', 150.00::numeric(12, 2), 150.00::numeric(12, 2), 0.00::numeric(12, 2)),
    (date '2026-02-02', 200.00::numeric(12, 2), 200.00::numeric(12, 2), 0.00::numeric(12, 2))
), actual_reconcile as (
  select
    sales_date,
    mart_gross_sales::numeric(12, 2),
    source_gross_sales::numeric(12, 2),
    diff_amount::numeric(12, 2)
  from marts.v_reconcile_sales_daily
)

select 'core.orders' as relation, 'unexpected' as divergence, row_to_json(t)::text as tuple
from (select * from actual_core_orders except select * from expected_core_orders) t
union all
select 'core.orders', 'missing', row_to_json(t)::text
from (select * from expected_core_orders except select * from actual_core_orders) t
union all
select 'marts.v_sales_daily', 'unexpected', row_to_json(t)::text
from (select * from actual_sales_daily except select * from expected_sales_daily) t
union all
select 'marts.v_sales_daily', 'missing', row_to_json(t)::text
from (select * from expected_sales_daily except select * from actual_sales_daily) t
union all
select 'marts.v_customer_state_daily', 'unexpected', row_to_json(t)::text
from (select * from actual_state_daily except select * from expected_state_daily) t
union all
select 'marts.v_customer_state_daily', 'missing', row_to_json(t)::text
from (select * from expected_state_daily except select * from actual_state_daily) t
union all
select 'marts.v_order_items_wide', 'unexpected', row_to_json(t)::text
from (select * from actual_items_wide except select * from expected_items_wide) t
union all
select 'marts.v_order_items_wide', 'missing', row_to_json(t)::text
from (select * from expected_items_wide except select * from actual_items_wide) t
union all
select 'marts.v_reconcile_sales_daily', 'unexpected', row_to_json(t)::text
from (select * from actual_reconcile except select * from expected_reconcile) t
union all
select 'marts.v_reconcile_sales_daily', 'missing', row_to_json(t)::text
from (select * from expected_reconcile except select * from actual_reconcile) t
union all
-- Row-count guards: EXCEPT is set-based, so exact duplicates would otherwise pass.
select 'core.order_items', 'wrong row count', count(*)::text from core.order_items having count(*) <> 4
union all
select 'marts.v_order_items_wide', 'wrong row count', count(*)::text from marts.v_order_items_wide having count(*) <> 4
union all
select 'marts.v_reconcile_sales_daily', 'wrong row count', count(*)::text from marts.v_reconcile_sales_daily having count(*) <> 2
;
