-- One batch must yield exactly one staging load timestamp.
--
-- Contract: this query must return ZERO rows. Every returned row is a failure
-- naming the relation, the kind of divergence, and the offending count.
--
-- The invariant is structural, not incidental. `now()` is transaction-start
-- time and `load_raw_csv_to_stg` wraps the truncate plus all four COPY calls in
-- one transaction, so every row of all four staging tables must carry an
-- identical `loaded_at`. More than one distinct value means the load was split
-- across more than one transaction, and the four sources could then report
-- inconsistent freshness.
--
-- This fails in both directions, and both are correct:
--   * more than one distinct value -> the load was not one transaction;
--   * zero distinct values         -> staging is entirely empty, which must
--                                     never be true at the point this runs.
--
-- Run it immediately after the seed, before anything backdates `loaded_at`.
-- Run after a backdate it would prove nothing about the load's own transaction.

select
  'stg.*' as relation,
  'loaded_at differs across staging tables' as divergence,
  count(*)::text as distinct_loaded_at_values
from (
  select distinct loaded_at from stg.orders
  union
  select distinct loaded_at from stg.order_items
  union
  select distinct loaded_at from stg.order_payments
  union
  select distinct loaded_at from stg.customers
) t
having count(*) <> 1
;
