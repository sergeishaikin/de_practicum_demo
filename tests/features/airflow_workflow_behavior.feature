@bdd @airflow
Feature: Fail-closed Airflow workflow behavior
  Maintenance and warehouse tasks protect state before publication proceeds.

  Scenario: Maintenance completes in the required order and records success
    Given a maintenance target with successful controlled boundaries
    When the actual maintenance task callable runs in Airflow
    Then maintenance operations run exactly in the required order
    And an ok maintenance audit is recorded

  Scenario: Snapshot expiry failure is audited and re-raised
    Given a maintenance target whose snapshot expiry fails
    When the actual maintenance task callable runs in Airflow
    Then no maintenance operation runs after snapshot expiry
    And a failed snapshot expiry audit is recorded
    And the original maintenance exception is re-raised

  Scenario: Four exact non-empty staging pairs are accepted
    Given four exact non-empty CSV and staging pairs
    When the actual staging validation task callable runs in Airflow
    Then staging validation succeeds

  Scenario: Empty staging is rejected
    Given one empty staging pair among the four inputs
    When the actual staging validation task callable runs in Airflow
    Then staging validation fails for the empty pair

  Scenario: Mismatched staging is rejected
    Given one mismatched staging pair among the four inputs
    When the actual staging validation task callable runs in Airflow
    Then staging validation fails for the mismatched pair

  Scenario: Zero-row core tables are ready and publish row-count metadata
    Given queryable core tables with zero rows
    When the actual core readiness and publisher callables run in Airflow
    Then core readiness succeeds and both row counts are published

  Scenario: Core readiness failure publishes no Asset metadata
    Given a core table that cannot be queried
    When the actual core readiness and publisher callables run in Airflow
    Then core readiness fails and no core metadata is published

  Scenario: Marts provenance comes from the source Asset DagRun
    Given a core orders event from a successful ingestion DagRun
    When the actual marts readiness callable runs in Airflow
    Then marts readiness returns the source ingestion run id

  Scenario: Ambiguous source events fail closed
    Given two core orders events from different ingestion DagRuns
    When the actual marts readiness callable runs in Airflow
    Then marts readiness rejects ambiguous source provenance

  Scenario: Payment mismatch prevents mart publication
    Given marts readiness followed by a payment mismatch
    When the actual marts quality and publisher callables run in Airflow
    Then payment reconciliation fails and no mart metadata is published

  Scenario: Payment match allows mart publication
    Given marts readiness followed by matching payments
    When the actual marts quality and publisher callables run in Airflow
    Then payment reconciliation succeeds and all mart metadata is published

  Scenario: Mart publication is refused when dbt validation did not succeed
    Given a marts run whose dbt artifact validation failed
    When the actual marts publisher callable runs in Airflow
    Then publication is refused, no audit is written and no mart metadata is published

  Scenario: A stale staging slice stops certification at the validator
    Given a marts run whose source freshness gate failed
    When the actual marts artifact validation callable runs in Airflow
    Then validation raises on the first poll and publication then refuses without auditing

  Scenario: A recovered marts run publishes the same way a clean run does
    Given a marts run whose dbt artifact validation succeeded
    When the actual marts publisher callable runs in Airflow
    Then the audit is written once and all mart metadata is published

  Scenario: Re-running the same DagRun updates the audit row instead of duplicating it
    Given a marts audit for a DagRun id that has already been recorded
    When the actual marts publisher callable runs in Airflow
    Then the audit statement upserts on the run id

  Scenario: Staging load truncates before every batch so a replay cannot accumulate rows
    Given a staging load for a repeated ingestion batch
    When the actual marts publisher callable runs in Airflow
    Then the truncate runs before any CSV is copied
