-- Cross-model invariant: the state-level mart must be a pure partition of the
-- daily mart. core.order_items carries exactly one customer_state per order, so
-- summing the state grain by day has to reproduce v_sales_daily exactly.
-- EXCEPT compares NULL sales_date groups as equal, and every column is an exact
-- type (bigint / numeric(12,2)), so no tolerance is needed.
--
-- Any returned row names the side that disagrees.

with rolled_up as (
  select
    sales_date,
    sum(orders_cnt)::bigint as orders_cnt,
    sum(items_cnt)::bigint as items_cnt,
    sum(gross_sales)::numeric(12, 2) as gross_sales
  from {{ ref('v_customer_state_daily') }}
  group by sales_date
), daily as (
  select
    sales_date,
    orders_cnt::bigint as orders_cnt,
    items_cnt::bigint as items_cnt,
    gross_sales::numeric(12, 2) as gross_sales
  from {{ ref('v_sales_daily') }}
)
select 'v_sales_daily' as unmatched_side, *
from (select * from daily except select * from rolled_up) as only_daily
union all
select 'v_customer_state_daily' as unmatched_side, *
from (select * from rolled_up except select * from daily) as only_rolled_up
