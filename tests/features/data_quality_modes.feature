@bdd @domain
Feature: Data quality enforcement modes
  The medallion inspects each bronze batch for broken data rules before curating
  it. Both enforcement modes are supported and must behave differently: in
  permissive mode a violation is evidence only, in strict mode it stops the cycle
  before anything is published.

  Scenario: A clean batch reports no violations
    Given a batch of well-formed orders
    When quality validation runs
    Then no quality violations are reported

  Scenario Outline: An order that breaks a data rule is counted as a violation
    Given a batch containing an order with <defect>
    When quality validation runs
    Then exactly 1 quality violation is reported

    Examples:
      | defect               |
      | a missing order id   |
      | a missing amount     |
      | an amount of zero    |
      | a negative amount    |
      | a missing country    |
      | an unknown status    |
      | a missing event time |

  Scenario: A field the batch does not carry is not a violation
    Given a batch that does not carry the country field
    When quality validation runs
    Then no quality violations are reported

  Scenario: A clean batch is curated and published
    Given a batch of well-formed orders
    When the medallion cycle runs in permissive mode
    Then the curated order state is published
    And the run is recorded as successful
    And the recorded violation count is 0

  Scenario: In permissive mode a violation is recorded but publication proceeds
    Given a batch containing an order with a missing order id
    When the medallion cycle runs in permissive mode
    Then the curated order state is published
    And the run is recorded as successful
    And the recorded violation count is 1

  Scenario: In strict mode a violation stops the cycle before publication
    Given a batch containing an order with a missing order id
    When the medallion cycle runs in strict mode
    Then nothing is published
    And the run is recorded as failed
    And the recorded violation count is 1
