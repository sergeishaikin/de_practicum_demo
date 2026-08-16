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

  Scenario: Payment mismatch prevents mart publication
    Given marts readiness followed by a payment mismatch
    When the actual marts quality and publisher callables run in Airflow
    Then payment reconciliation fails and no mart metadata is published
