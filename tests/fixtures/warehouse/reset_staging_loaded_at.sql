-- Restore the staging load timestamp after a deliberate backdate.
--
-- DESTRUCTIVE, CI-ONLY. The counterpart to
-- tests/fixtures/warehouse/backdate_staging_loaded_at.sql. In CI this runs with
-- `if: always()`, so a red stale-freshness step cannot leave staging backdated
-- for the steps that follow — `dbt build`, the mart assertions, replay parity
-- and the mutation gate all run afterwards against this same database. The
-- guard below aborts if marts.pipeline_runs holds rows, i.e. if this is a real
-- warehouse that a pipeline run has already published to.
--
-- The single transaction is load-bearing, not stylistic. `now()` is
-- transaction-start time, so wrapping all four updates in one transaction
-- restores exactly the invariant the load itself produces and that
-- assert_loaded_at_is_one_batch.sql checks: one batch, one timestamp, across
-- all four staging tables. Four separate transactions would leave four
-- different values and quietly break that invariant while looking like a reset.

begin;

do $$
begin
  if (select count(*) from marts.pipeline_runs) > 0 then
    raise exception
      'Refusing to reset staging loaded_at: marts.pipeline_runs is not empty, this looks like a real warehouse';
  end if;
end
$$;

update stg.orders set loaded_at = now();
update stg.order_items set loaded_at = now();
update stg.order_payments set loaded_at = now();
update stg.customers set loaded_at = now();

commit;
