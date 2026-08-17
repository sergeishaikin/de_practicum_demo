@bdd @domain
Feature: Safe legacy outbox cleanup
  A legacy batch may only be deleted once its rows are provably represented in
  authoritative state, nothing is still processing it, and the proposed deletion
  set matches an explicit human approval. Every rejection must happen before any
  batch is touched.

  Scenario: A fully reconciled legacy batch is eligible for cleanup
    Given a legacy batch whose rows are represented in authoritative state
    When the legacy batches are classified
    Then the batch is eligible for cleanup
    And the proposed cleanup set contains exactly that batch

  Scenario: A batch still being processed is not eligible, even once its rows are migrated
    Given a legacy batch whose rows are represented in authoritative state
    And the batch is still being processed
    When the legacy batches are classified
    Then the batch is not eligible for cleanup
    And the proposed cleanup set is empty
    And the batch is withheld because it is still being processed

  Scenario: A batch whose rows are missing from authoritative state is not eligible
    Given a legacy batch whose rows are absent from authoritative state
    When the legacy batches are classified
    Then the batch is not eligible for cleanup
    And the proposed cleanup set is empty
    And the batch is withheld as unsafe

  Scenario: Work created after the migration boundary is live, not stale
    Given a legacy batch whose rows are represented in authoritative state
    And the batch was created after the migration boundary
    When the legacy batches are classified
    Then the batch is not eligible for cleanup
    And the proposed cleanup set is empty
    And the batch is reported as live work rather than withheld as unsafe

  Scenario: The approval fingerprint does not depend on the order of batches
    Given two proposed batches in one order
    And the same two batches in the opposite order
    When both fingerprints are taken
    Then the two fingerprints are identical

  Scenario: Cleanup is refused when any batch is still being processed
    Given a cleanup approval that matches the approved batch count
    And the approval reports a batch that is still being processed
    When the cleanup gate runs
    Then cleanup is refused because a batch is still being processed

  Scenario: Cleanup is refused on a fingerprint mismatch before any batch is inspected
    Given a cleanup approval that matches the approved batch count
    And the approval fingerprint does not match the recorded approval
    And the approval proposes a batch stored outside the outbox
    When the cleanup gate runs
    Then cleanup is refused because the fingerprint does not match

  Scenario: Cleanup is refused when redundancy cannot be proven at all
    Given a cleanup approval that matches the approved batch count
    And current state cannot prove the batches are redundant
    When the cleanup gate runs
    Then cleanup is refused because redundancy cannot be proven
    And the refusal explains the unproven state rather than blaming the approval
