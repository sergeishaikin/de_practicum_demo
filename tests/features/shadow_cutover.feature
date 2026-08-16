@bdd @domain
Feature: Shadow validation and the metrics source cutover
  Daily metrics may be served either from a full rebuild of the current business
  state or from the state the pipeline maintains incrementally. Moving between
  those two sources is a staged rollout, not a switch: while both projections are
  produced they must agree before anything is published, and changing which one
  feeds the metrics must never rewrite the incrementally maintained state.

  Rollout stages are named states, and only the stages below exist. Serving
  metrics from the incrementally maintained state while shadow validation is
  disabled would publish unvalidated business state and is refused at startup.

  Rolling back changes only which source feeds the metrics. It returns the
  deployment to the earlier validating state — it is not a move to a separate
  terminal state with validation switched off.

  Scenario Outline: Each stage of the rollout is a supported runtime state
    Given a runtime configured for the <stage> stage
    When the rollout configuration is validated
    Then the runtime is accepted as the <stage> stage

    Examples:
      | stage    |
      | legacy   |
      | rollback |
      | shadow   |
      | cutover  |

  Scenario: Serving metrics from the incremental state without shadow validation is refused
    Given a runtime that serves metrics from the incremental state with shadow validation disabled
    When the rollout configuration is validated
    Then the runtime is refused as unsafe

  Scenario: Agreeing projections publish the daily metrics
    Given an incremental business state that agrees with a full rebuild
    When the cycle runs under shadow validation
    Then the daily metrics are published
    And the run is recorded as successful
    And exactly 1 shadow comparison is recorded

  Scenario: A disagreement stops the cycle before any metrics are published
    Given an incremental business state that disagrees with a full rebuild
    When the cycle runs under shadow validation
    Then the cycle fails closed
    And no daily metrics are published
    And the run is recorded as a shadow failure
    And the disagreement is counted in the recorded evidence

  Scenario: Both projections are compared at the same pinned source boundary
    Given an incremental business state that agrees with a full rebuild
    And later observations arrive while the incremental run is in progress
    When the cycle runs under shadow validation
    Then the daily metrics are published
    And the run is recorded as successful

  Scenario: Metrics served from the incremental state do not rewrite it
    Given an incremental business state that agrees with a full rebuild
    When the cycle runs with metrics served from the incremental state
    Then the daily metrics are published
    And the incremental business state is not rewritten

  Scenario: Rolling the metrics source back returns to the validating state
    Given an incremental business state that agrees with a full rebuild
    And a completed cycle with metrics served from the incremental state
    When the metrics source is rolled back to the full rebuild
    Then the daily metrics are published again
    And the incremental business state is not rewritten
    And shadow validation is still in force
