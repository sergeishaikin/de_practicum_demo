select
  sales_date,
  orders_cnt,
  items_cnt,
  gross_sales,
  freight_sum
from marts.v_sales_daily
order by sales_date
limit 15;

select
  customer_state,
  sum(orders_cnt) as orders_cnt,
  sum(items_cnt) as items_cnt,
  sum(gross_sales)::numeric(12, 2) as gross_sales
from marts.v_customer_state_daily
group by customer_state
order by gross_sales desc
limit 10;
