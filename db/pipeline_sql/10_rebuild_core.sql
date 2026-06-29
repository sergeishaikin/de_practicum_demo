begin;

truncate table
  core.order_items,
  core.orders;

insert into core.orders (
  order_id,
  customer_id,
  customer_state,
  order_status,
  order_purchase_date,
  payment_value,
  main_payment_type,
  max_installments,
  ingest_date
)
with payment_agg as (
  select
    order_id,
    ingest_date,
    sum(payment_value)::numeric(12, 2) as payment_value,
    (array_agg(payment_type order by payment_value desc, payment_sequential))[1] as main_payment_type,
    max(payment_installments)::int as max_installments
  from stg.order_payments
  group by order_id, ingest_date
)
select
  o.order_id,
  o.customer_id,
  c.customer_state,
  o.order_status,
  o.order_purchase_timestamp::date as order_purchase_date,
  pa.payment_value,
  pa.main_payment_type,
  pa.max_installments,
  o.ingest_date
from stg.orders o
join stg.customers c
  on c.customer_id = o.customer_id
 and c.ingest_date = o.ingest_date
left join payment_agg pa
  on pa.order_id = o.order_id
 and pa.ingest_date = o.ingest_date;

insert into core.order_items (
  order_id,
  order_item_id,
  order_purchase_date,
  order_status,
  customer_id,
  customer_state,
  product_id,
  seller_id,
  price,
  freight_value,
  ingest_date
)
select
  oi.order_id,
  oi.order_item_id,
  o.order_purchase_date,
  o.order_status,
  o.customer_id,
  o.customer_state,
  oi.product_id,
  oi.seller_id,
  oi.price,
  oi.freight_value,
  oi.ingest_date
from stg.order_items oi
join core.orders o
  on o.order_id = oi.order_id;

commit;
