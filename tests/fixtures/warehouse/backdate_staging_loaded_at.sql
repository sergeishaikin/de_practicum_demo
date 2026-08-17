-- Backdate the staging load timestamp so `dbt source freshness` must fail.
--
-- DESTRUCTIVE, CI-ONLY. Paired with tests/fixtures/warehouse/reset_staging_loaded_at.sql,
-- which MUST run afterwards — in CI it runs with `if: always()`, so a red stale
-- step cannot leave staging backdated. The guard below aborts if
-- marts.pipeline_runs holds rows, i.e. if this is a real warehouse that a
-- pipeline run has already published to.
--
-- Three hours exceeds the configured `error_after` of 2 hours with margin, so
-- the result is an error rather than a warn, and dbt exits 1 rather than 0.
--
-- Deterministic by construction. There is no sleep and no wall-clock coupling
-- anywhere: `loaded_at` is a column under test control, so staleness is
-- produced by writing it, not by waiting for it. That is what keeps the
-- freshness layer from becoming the flaky part of the suite.
--
-- All four tables are backdated, not just stg.orders. One error result is
-- already enough to flip the exit code, but updating a single table would
-- invite a reader to conclude the other three are exempt from the invariant.

begin;

do $$
begin
  if (select count(*) from marts.pipeline_runs) > 0 then
    raise exception
      'Refusing to backdate staging loaded_at: marts.pipeline_runs is not empty, this looks like a real warehouse';
  end if;
end
$$;

update stg.orders set loaded_at = now() - interval '3 hours';
update stg.order_items set loaded_at = now() - interval '3 hours';
update stg.order_payments set loaded_at = now() - interval '3 hours';
update stg.customers set loaded_at = now() - interval '3 hours';

commit;
