-- Step 2 of the replay-parity check: re-processing the same staging batch must
-- not change the business result.
--
-- This is the property that makes the batch pipeline safe to retry. An Airflow
-- retry, a manual re-trigger, or a partially-failed run followed by a rerun all
-- replay the same staging slice through db/pipeline_sql/10_rebuild_core.sql. If
-- that path were not idempotent, a retry would silently change reported sales.
--
-- Contract: this query must return ZERO rows. Every returned row names the
-- relation and the direction of the divergence. EXCEPT is symmetric-differenced
-- both ways so added and dropped rows are both caught, and it treats NULLs as
-- equal, which is what we want when comparing whole rows.

select 'core.orders' as relation, 'appeared on replay' as divergence, row_to_json(t)::text as tuple
from (select * from core.orders except select * from replay_check.core_orders) t
union all
select 'core.orders', 'lost on replay', row_to_json(t)::text
from (select * from replay_check.core_orders except select * from core.orders) t
union all
select 'core.order_items', 'appeared on replay', row_to_json(t)::text
from (select * from core.order_items except select * from replay_check.core_order_items) t
union all
select 'core.order_items', 'lost on replay', row_to_json(t)::text
from (select * from replay_check.core_order_items except select * from core.order_items) t
union all
select 'marts.v_sales_daily', 'appeared on replay', row_to_json(t)::text
from (select * from marts.v_sales_daily except select * from replay_check.v_sales_daily) t
union all
select 'marts.v_sales_daily', 'lost on replay', row_to_json(t)::text
from (select * from replay_check.v_sales_daily except select * from marts.v_sales_daily) t
union all
select 'marts.v_customer_state_daily', 'appeared on replay', row_to_json(t)::text
from (select * from marts.v_customer_state_daily except select * from replay_check.v_customer_state_daily) t
union all
select 'marts.v_customer_state_daily', 'lost on replay', row_to_json(t)::text
from (select * from replay_check.v_customer_state_daily except select * from marts.v_customer_state_daily) t
union all
select 'marts.v_order_items_wide', 'appeared on replay', row_to_json(t)::text
from (select * from marts.v_order_items_wide except select * from replay_check.v_order_items_wide) t
union all
select 'marts.v_order_items_wide', 'lost on replay', row_to_json(t)::text
from (select * from replay_check.v_order_items_wide except select * from marts.v_order_items_wide) t
union all
select 'marts.v_reconcile_sales_daily', 'appeared on replay', row_to_json(t)::text
from (select * from marts.v_reconcile_sales_daily except select * from replay_check.v_reconcile_sales_daily) t
union all
select 'marts.v_reconcile_sales_daily', 'lost on replay', row_to_json(t)::text
from (select * from replay_check.v_reconcile_sales_daily except select * from marts.v_reconcile_sales_daily) t
union all
-- Row-count guards: EXCEPT is set-based, so an exact duplicate row would slip past it.
select 'core.orders', 'row count changed',
  (select count(*) from replay_check.core_orders)::text || ' -> ' || (select count(*) from core.orders)::text
where (select count(*) from core.orders) <> (select count(*) from replay_check.core_orders)
union all
select 'core.order_items', 'row count changed',
  (select count(*) from replay_check.core_order_items)::text || ' -> ' || (select count(*) from core.order_items)::text
where (select count(*) from core.order_items) <> (select count(*) from replay_check.core_order_items)
;
