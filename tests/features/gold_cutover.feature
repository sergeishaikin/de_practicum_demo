@bdd @integration
Feature: Gold cutover and rollback
  Moving the daily metrics onto the incrementally maintained business state is a
  staged deployment, walked one accepted stage at a time:

      full rebuild serves the metrics, both projections validated
        -> the incremental state serves the metrics, still validated
        -> the metrics source is rolled back to the full rebuild

  The invariant across the whole walk: cutover and rollback select **which Silver
  projection serves Gold**. They do not toggle the incremental Silver pipeline
  itself, which keeps running and keeps owning the current business state.

  Rollback therefore returns the deployment to a stage it already occupied, not to
  a new terminal stage with validation switched off. Serving the metrics from the
  incremental state without validation is not an accepted stage at all, and the
  service refuses to start in it.

  The rules about *what* a comparison decides are specified in
  shadow_cutover.feature against in-memory doubles. This feature adds only what a
  live catalog can show: that the accepted stages survive real deployments, that
  the persisted state carries the same Iceberg snapshots across them, and that an
  unaccepted stage never reaches a running service.

  Scenario: The accepted sequence serves metrics at every stage without rewriting the incremental state
    Given a lake holding two batches of committed order observations
    When the deployment serves metrics from the full rebuild
    Then the daily metrics are published
    And the incremental business state holds the current version of each order

    When the metrics source is switched to the incremental state
    Then the daily metrics are unchanged
    And the incremental business state is untouched

    When the metrics source is rolled back to the full rebuild
    Then the daily metrics are unchanged
    And the incremental business state is untouched

  Scenario: A certified comparison is not repeated by a later deployment
    Given a lake holding two batches of committed order observations
    When the deployment serves metrics from the full rebuild
    Then the daily metrics are published
    And the incremental business state holds the current version of each order

    When the metrics source is switched to the incremental state
    Then the daily metrics are unchanged
    And the incremental business state is untouched

    When a second deployment serves metrics from the incremental state
    Then it announces a cycle that skipped both the comparison and the rebuild
    And the daily metrics are unchanged
    And the incremental business state is untouched
    And the daily metrics table gained no snapshot

  Scenario: A deployment that serves metrics from the incremental state without validation refuses to start
    Given a lake holding two batches of committed order observations
    When a deployment is started that serves metrics from the incremental state with validation disabled
    Then the service exits instead of running
    And it reports the configuration as unsafe
    And no daily metrics are published
