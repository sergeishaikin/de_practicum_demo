@bdd @integration
Feature: Safe Iceberg writer publication
  The writer publishes landing data into Bronze only when Spark has declared it
  committed, and every publication records the load identity that later lets a
  restart tell whether the batch is already in the table.

  Crash and restart semantics are specified separately in
  writer_crash_recovery.feature and are deliberately not restated here.

  Scenario: Landing data Spark has not committed is not published
    Given a landing file of 5 orders that Spark has not committed
    When the writer runs and settles
    Then nothing is published

  Scenario: A publication records its load identity in the table's own evidence
    Given a committed landing batch of 5 orders
    When the writer runs and settles
    Then the batch is published exactly once
    And the publication records exactly one load identity

  Scenario: Commit evidence the writer cannot interpret prevents publication
    Given a landing file of 5 orders with unreadable commit evidence
    When the writer runs and settles
    Then nothing is published
