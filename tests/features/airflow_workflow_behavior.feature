@bdd @airflow
Feature: Fail-closed Airflow workflow behavior
  The maintenance and staging tasks protect state before the workflow proceeds.

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
