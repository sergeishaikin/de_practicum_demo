{{ config(alias='v_reconcile_sales_daily', tags=['contract:reconciliation', 'criticality:tier1']) }}

with source_sales as (
  select
    o.order_purchase_timestamp::date as sales_date,
    sum(oi.price)::numeric(12, 2) as source_gross_sales
  from {{ source('staging', 'orders') }} o
  inner join {{ source('staging', 'order_items') }} oi
    on oi.order_id = o.order_id
   and oi.ingest_date = o.ingest_date
  group by o.order_purchase_timestamp::date
)
select
  coalesce(m.sales_date, s.sales_date) as sales_date,
  coalesce(m.gross_sales, 0)::numeric(12, 2) as mart_gross_sales,
  coalesce(s.source_gross_sales, 0)::numeric(12, 2) as source_gross_sales,
  (coalesce(m.gross_sales, 0) - coalesce(s.source_gross_sales, 0))::numeric(12, 2) as diff_amount
from {{ ref('v_sales_daily') }} m
full join source_sales s
  on s.sales_date = m.sales_date
