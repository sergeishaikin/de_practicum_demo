{{ config(materialized='view', alias='current_orders') }}

{# Thin semantic alias; B2 remains the version-resolution owner. #}
select
    order_id,
    customer,
    amount,
    country,
    status,
    event_time,
    event_date,
    business_version
from {{ source('silver', 'orders_clean') }}
