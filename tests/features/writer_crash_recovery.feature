@bdd @integration
Feature: Writer recovery preserves exactly-once publication
  The writer records a load identity with every append and re-checks it against
  the table's own snapshot history when it restarts. A crash on either side of
  the commit boundary must therefore leave the same published result: the batch
  appears exactly once.

  Scenario: Restart after a committed append does not append the batch again
    Given a committed landing batch of 5 orders
    When the writer crashes immediately after committing the batch
    Then the batch is published exactly once
    And exactly one outbox record exists
    When the writer restarts and settles
    Then the batch is still published exactly once
    And no batch remains pending
    And the source file is recorded as done
    And exactly one outbox record exists

  Scenario: Restart after a crash before commit appends the batch exactly once
    Given a committed landing batch of 5 orders
    When the writer crashes immediately before committing the batch
    And the writer restarts and publishes the pending batch
    Then the batch is published exactly once
    And the source file is recorded as done
    And exactly one outbox record exists
