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

-- The four `marts.v_*` views are deliberately NOT created here. dbt owns their
-- definition (`dbt/warehouse/models/marts/`), and a bootstrap copy would give the
-- database two different architectures: `core -> marts` before dbt has run and
-- `core -> staging -> marts` after it. Nothing in dbt can see a view defined in
-- this file, so the copy could drift without any gate noticing.
--
-- Consequence: the mart views do not exist until `dbt build` runs. Anything that
-- reads them - `scripts/show_layers`, `scripts/run_checks`, the HTML report - needs
-- a completed ingestion run first. See docs/warehouse/W1-dbt-ownership.md.
