-- Deterministic staging seed for the warehouse staging -> core -> marts ->
-- reconciliation integration check.
--
-- DESTRUCTIVE: truncates stg.* and is followed by db/pipeline_sql/10_rebuild_core.sql,
-- which truncates core.*. Intended for an ephemeral CI database only. The guard
-- below aborts if marts.pipeline_runs holds rows, i.e. if this is a real
-- warehouse that a pipeline run has already published to.
--
-- The scenario is deliberately richer than one row so the assertions can fail:
--   ord-1  cust-1 (BE)  2026-02-01  2 items  20.00 + 30.00   payments 40.00 + 15.00
--   ord-2  cust-2 (NL)  2026-02-01  1 item  100.00           payment  105.00
--   ord-3  cust-3 (BE)  2026-02-02  1 item  200.00           payment  210.00
-- It exercises multi-item orders, several orders per day, several days, several
-- customer states, and multi-row payment aggregation with a non-obvious winner
-- for main_payment_type.

begin;

do $$
begin
  if (select count(*) from marts.pipeline_runs) > 0 then
    raise exception
      'Refusing to seed: marts.pipeline_runs is not empty, this looks like a real warehouse';
  end if;
end
$$;

truncate table
  stg.orders,
  stg.order_items,
  stg.order_payments,
  stg.customers;

insert into stg.customers
  (customer_id, customer_unique_id, customer_zip_code_prefix, customer_city, customer_state, ingest_date)
values
  ('cust-1', 'cust-1-u', '1000', 'Brussels', 'BE', date '2026-02-01'),
  ('cust-2', 'cust-2-u', '1011', 'Amsterdam', 'NL', date '2026-02-01'),
  ('cust-3', 'cust-3-u', '2000', 'Antwerp', 'BE', date '2026-02-01');

insert into stg.orders
  (order_id, customer_id, order_status, order_purchase_timestamp, order_approved_at,
   order_delivered_carrier_date, order_delivered_customer_date, order_estimated_delivery_date, ingest_date)
values
  ('ord-1', 'cust-1', 'paid', timestamp '2026-02-01 09:00:00', null, null, null, null, date '2026-02-01'),
  ('ord-2', 'cust-2', 'paid', timestamp '2026-02-01 15:00:00', null, null, null, null, date '2026-02-01'),
  ('ord-3', 'cust-3', 'canceled', timestamp '2026-02-02 11:00:00', null, null, null, null, date '2026-02-01');

insert into stg.order_items
  (order_id, order_item_id, product_id, seller_id, shipping_limit_date, price, freight_value, ingest_date)
values
  ('ord-1', 1, 'prod-1', 'sell-1', timestamp '2026-02-05 00:00:00', 20.00, 2.00, date '2026-02-01'),
  ('ord-1', 2, 'prod-2', 'sell-1', timestamp '2026-02-05 00:00:00', 30.00, 3.00, date '2026-02-01'),
  ('ord-2', 1, 'prod-3', 'sell-2', timestamp '2026-02-05 00:00:00', 100.00, 5.00, date '2026-02-01'),
  ('ord-3', 1, 'prod-4', 'sell-3', timestamp '2026-02-06 00:00:00', 200.00, 10.00, date '2026-02-01');

insert into stg.order_payments
  (order_id, payment_sequential, payment_type, payment_installments, payment_value, ingest_date)
values
  ('ord-1', 1, 'credit_card', 3, 40.00, date '2026-02-01'),
  ('ord-1', 2, 'voucher', 1, 15.00, date '2026-02-01'),
  ('ord-2', 1, 'boleto', 1, 105.00, date '2026-02-01'),
  ('ord-3', 1, 'credit_card', 1, 210.00, date '2026-02-01');

commit;
