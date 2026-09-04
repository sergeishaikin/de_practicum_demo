## ADDED Requirements

### Requirement: An optimisation is justified against a measured baseline

WHEN a measurement is used to argue that a code path is worth optimising, the
argument SHALL express that path's cost as a share of a baseline measured on the
same system in the same state. An absolute duration SHALL NOT stand in for that
share, and a baseline produced by different code SHALL NOT be substituted for
one that was never measured.

Absent the baseline, the honest conclusion is that the question is unanswerable
on present evidence. Recording that is a complete outcome; manufacturing a
denominator to reach a decision is not.

#### Scenario: The baseline was never produced

- **WHEN** the profile of a code path exists but the cycle it would be compared
  against does not
- **THEN** the missing input is named and the reason for its absence recorded
- **AND** no substitute denominator is derived, and no optimisation is made

#### Scenario: A microbenchmark stands in for production cost

- **WHEN** a measurement is taken over synthetic data outside the running system
- **THEN** it is recorded as bounding the cost rather than predicting it, with
  the conditions it does not reproduce stated beside its numbers
