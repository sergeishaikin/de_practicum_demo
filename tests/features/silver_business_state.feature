@bdd @domain
Feature: Silver current business state
  Silver holds exactly one current row per order. The business version is the only
  authority on which observation is current — the order in which observations
  arrive over the transport must never decide, and a batch that cannot be resolved
  leaves the existing state untouched.

  Scenario: A later business version replaces an earlier version
    Given a current order "order-1" at business version 1 with amount 10
    And an incoming order "order-1" at business version 2 with amount 20
    When the incoming observations are resolved against current state
    Then exactly 1 order becomes current
    And order "order-1" is current at business version 2 with amount 20

  Scenario: Transport arrival order cannot override business version
    Given an observed order "order-1" at business version 5 with amount 50 at transport offset 1
    And an observed order "order-1" at business version 3 with amount 30 at transport offset 99
    When the current business state is rebuilt from all observations
    Then exactly 1 order is current
    And order "order-1" is current at business version 5 with amount 50

  Scenario: An older business version arriving later does not regress state
    Given a current order "order-1" at business version 5 with amount 50
    And an incoming order "order-1" at business version 3 with amount 30
    When the incoming observations are resolved against current state
    Then no order becomes current
    And the previously current state is unchanged

  Scenario: A repeated identical observation changes nothing
    Given a current order "order-1" at business version 5 with amount 50
    And an incoming order "order-1" at business version 5 with amount 50
    When the incoming observations are resolved against current state
    Then no order becomes current
    And the previously current state is unchanged

  Scenario: The same business version with a conflicting payload is rejected
    Given a current order "order-1" at business version 5 with amount 50
    And an incoming order "order-1" at business version 5 with amount 51
    When the incoming observations are resolved against current state
    Then the batch is rejected as a business version conflict

  Scenario: A rejected batch is not partially applied
    Given a current order "order-1" at business version 5 with amount 50
    And an incoming order "order-1" at business version 5 with amount 51
    And an incoming order "order-2" at business version 1 with amount 10
    When the incoming observations are resolved against current state
    Then the batch is rejected as a business version conflict
    And no change is available to apply for order "order-2"
    And the previously current state is unchanged

  Scenario: Many observations for one order collapse to a single current row
    Given no current order state
    And an incoming order "order-1" at business version 3 with amount 30
    And an incoming order "order-1" at business version 5 with amount 50
    And an incoming order "order-2" at business version 2 with amount 20
    When the incoming observations are resolved against current state
    Then exactly 2 orders become current
    And order "order-1" is current at business version 5 with amount 50
    And order "order-2" is current at business version 2 with amount 20

  Scenario: A version change that moves an order to another day leaves one current row
    Given an observed order "order-1" at business version 1 with amount 10 on 2026-08-08 at transport offset 1
    And an observed order "order-1" at business version 2 with amount 20 on 2026-08-09 at transport offset 2
    When the current business state is rebuilt from all observations
    Then exactly 1 order is current
    And order "order-1" is current at business version 2 with amount 20
