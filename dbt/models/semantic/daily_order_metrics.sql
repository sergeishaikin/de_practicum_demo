{{ config(materialized='view', alias='daily_order_metrics') }}

{# Thin semantic alias; D-4 remains the aggregate owner. #}
select
    event_date as order_date,
    country,
    status,
    orders_count,
    total_amount,
    avg_amount,
    distinct_customers
from {{ source('gold', 'orders_daily_metrics') }}
