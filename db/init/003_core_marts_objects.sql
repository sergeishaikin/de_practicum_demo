create table if not exists core.orders (
  order_id varchar primary key,
  customer_id varchar not null,
  customer_state varchar,
  order_status varchar,
  order_purchase_date date,
  payment_value numeric(12, 2),
  main_payment_type varchar,
  max_installments int,
  ingest_date date not null
);

create table if not exists core.order_items (
  order_id varchar not null,
  order_item_id int not null,
  order_purchase_date date,
  order_status varchar,
  customer_id varchar not null,
  customer_state varchar,
  product_id varchar not null,
  seller_id varchar not null,
  price numeric(12, 2),
  freight_value numeric(12, 2),
  ingest_date date not null,
  primary key (order_id, order_item_id)
);

create or replace view marts.v_order_items_wide as
select
  oi.order_id,
  oi.order_item_id,
  oi.order_purchase_date,
  oi.order_status,
  oi.customer_id,
  oi.customer_state,
  oi.product_id,
  oi.seller_id,
  oi.price,
  oi.freight_value,
  o.payment_value as order_payment_value,
  o.main_payment_type,
  oi.ingest_date
from core.order_items oi
left join core.orders o
  on o.order_id = oi.order_id;

create or replace view marts.v_sales_daily as
select
  order_purchase_date as sales_date,
  count(distinct order_id) as orders_cnt,
  count(*) as items_cnt,
  sum(price)::numeric(12, 2) as gross_sales,
  sum(freight_value)::numeric(12, 2) as freight_sum
from core.order_items
group by order_purchase_date;

create or replace view marts.v_customer_state_daily as
select
  order_purchase_date as sales_date,
  customer_state,
  count(distinct order_id) as orders_cnt,
  count(*) as items_cnt,
  sum(price)::numeric(12, 2) as gross_sales
from core.order_items
group by order_purchase_date, customer_state;

create or replace view marts.v_reconcile_sales_daily as
with source_sales as (
  select
    o.order_purchase_timestamp::date as sales_date,
    sum(oi.price)::numeric(12, 2) as source_gross_sales
  from stg.orders o
  join stg.order_items oi
    on oi.order_id = o.order_id
   and oi.ingest_date = o.ingest_date
  group by o.order_purchase_timestamp::date
)
select
  coalesce(m.sales_date, s.sales_date) as sales_date,
  coalesce(m.gross_sales, 0)::numeric(12, 2) as mart_gross_sales,
  coalesce(s.source_gross_sales, 0)::numeric(12, 2) as source_gross_sales,
  (coalesce(m.gross_sales, 0) - coalesce(s.source_gross_sales, 0))::numeric(12, 2) as diff_amount
from marts.v_sales_daily m
full join source_sales s
  on s.sales_date = m.sales_date;
