create table if not exists stg.orders (
  order_id varchar,
  customer_id varchar,
  order_status varchar,
  order_purchase_timestamp timestamp,
  order_approved_at timestamp,
  order_delivered_carrier_date timestamp,
  order_delivered_customer_date timestamp,
  order_estimated_delivery_date timestamp,
  ingest_date date not null,
  primary key (order_id, ingest_date)
);

create table if not exists stg.order_items (
  order_id varchar,
  order_item_id int,
  product_id varchar,
  seller_id varchar,
  shipping_limit_date timestamp,
  price numeric(12, 2),
  freight_value numeric(12, 2),
  ingest_date date not null,
  primary key (order_id, order_item_id, ingest_date)
);

create table if not exists stg.order_payments (
  order_id varchar,
  payment_sequential int,
  payment_type varchar,
  payment_installments int,
  payment_value numeric(12, 2),
  ingest_date date not null,
  primary key (order_id, payment_sequential, ingest_date)
);

create table if not exists stg.customers (
  customer_id varchar,
  customer_unique_id varchar,
  customer_zip_code_prefix varchar,
  customer_city varchar,
  customer_state varchar,
  ingest_date date not null,
  primary key (customer_id, ingest_date)
);

create index if not exists ix_stg_orders_customer on stg.orders(customer_id);
create index if not exists ix_stg_order_payments_order on stg.order_payments(order_id);
