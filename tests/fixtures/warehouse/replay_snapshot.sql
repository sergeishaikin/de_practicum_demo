-- Step 1 of the replay-parity check: freeze the business result of the first
-- rebuild so a second rebuild of the *same* staging batch can be compared to it.
--
-- Run order:
--   seed_staging.sql -> 10_rebuild_core.sql -> replay_snapshot.sql
--     -> 10_rebuild_core.sql (again) -> assert_replay_parity.sql
--
-- Snapshots live in their own schema so nothing in core/marts is disturbed.

begin;

drop schema if exists replay_check cascade;
create schema replay_check;

create table replay_check.core_orders as
  select * from core.orders;
create table replay_check.core_order_items as
  select * from core.order_items;
create table replay_check.v_sales_daily as
  select * from marts.v_sales_daily;
create table replay_check.v_customer_state_daily as
  select * from marts.v_customer_state_daily;
create table replay_check.v_order_items_wide as
  select * from marts.v_order_items_wide;
create table replay_check.v_reconcile_sales_daily as
  select * from marts.v_reconcile_sales_daily;

commit;
