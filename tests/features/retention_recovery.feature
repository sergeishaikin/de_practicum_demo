@bdd @domain
Feature: Snapshot retention protects writer recovery
  A restarting writer decides whether a pending batch was already committed by
  reading Bronze snapshot summaries. Maintenance must therefore keep snapshots
  strictly longer than the window in which that evidence can still be needed —
  expiring them exactly at the boundary already destroys the signal.

  Scenario: Retention beyond the recovery boundary is accepted
    Given a recovery horizon of 1h
    And a safety margin of 15m
    When snapshot retention is set to 2h
    Then the retention contract is accepted

  Scenario: Retention exactly at the recovery boundary is rejected
    Given a recovery horizon of 1h
    And a safety margin of 15m
    When snapshot retention is set to 75m
    Then the retention contract is rejected as unsafe for recovery

  Scenario: A retention period that cannot be interpreted is rejected
    Given a recovery horizon of 1h
    And a safety margin of 15m
    When snapshot retention is set to sometime-tomorrow
    Then the configuration is rejected
