# Verification contract

What counts as verified in this repository.

## Purpose

`AGENTS.md` holds the canonical commands of the completion gate, and it stays
the single place those commands are written down — this spec deliberately does
not copy them, because two copies of a command list drift. What this spec adds
is the rule set around them: which claims may be made, on what evidence, and
what must be said when a check could not run.

## Requirements

### Requirement: A check is only reported as passed if it was executed

A verification claim SHALL name the command that produced it and the figures it
returned. A check that was not run SHALL be reported as not run.

#### Scenario: A gate needs a live stack that is not authorised

- **WHEN** an artifact names a check requiring services the task may not start
- **THEN** the report names that check as not executed, names the substitute
  that was executed instead, and states what remains unproven

#### Scenario: A step passes without doing anything

- **WHEN** a CI step reports success
- **THEN** the evidence quotes the test counts, because a step that collected
  zero tests also reports success

### Requirement: Stateful systems are not touched without authorisation

Docker, Kafka, Spark, MinIO, PostgreSQL and Iceberg SHALL be treated as
stateful. Read-only analysis SHALL NOT start or stop services, roll
checkpoints, publish records or mutate tables.

#### Scenario: Diagnosis requires a running service

- **WHEN** an investigation cannot proceed without starting a service
- **THEN** it stops and asks, naming the minimum that must run, rather than
  starting the stack and reporting afterwards

### Requirement: Cold-start evidence belongs to the clean-rebuild workflow

Proof that the stack works from empty volumes SHALL come from the H1 clean
workflow, which owns the destructive fresh-volume run.

#### Scenario: A local proof is tempting

- **WHEN** a defect appears to be cold-start specific
- **THEN** it is proved by the clean workflow rather than by a local
  `down -v`, so the destructive step has exactly one owner

### Requirement: A fix is proved by a test that fails without it

A behavioural fix SHALL be accompanied by a check demonstrated to fail against
the unfixed code.

#### Scenario: A regression contract is added

- **WHEN** a defect is repaired
- **THEN** the new test is run against the pre-fix state and shown to fail, and
  that demonstration is recorded with the fix

### Requirement: An operational gate is not reinterpreted after it fails

WHEN a gate was set as the condition for proceeding, its meaning SHALL NOT be
weakened because it failed.

#### Scenario: A gate fails for an unrelated reason

- **WHEN** the gate's stated blockers are fixed but the gate is still red for a
  newly discovered reason
- **THEN** the condition is treated as unmet, and the new failure is classified
  before the dependent work proceeds

### Requirement: A closed set of accepted states is asserted by equality

WHEN a constant enumerates the states a system is allowed to run in, the check
that guards it SHALL assert set equality against the intended states, not
membership of a sample. Adding a state SHALL fail that check, and removing one
SHALL fail it too.

A membership assertion passes for a superset. It therefore reports success while
testing less than it appears to, which no other rule in this spec catches: the
check was executed, and it did fail before its fix, but it does not detect the
change it exists to detect.

#### Scenario: A new accepted state is added to the constant

- **WHEN** a key is added to a constant enumerating accepted runtime states
- **THEN** the guarding check fails, so the addition has to be argued for as an
  architectural decision rather than arriving as an unnoticed entry

#### Scenario: The assertion is proved rather than assumed

- **WHEN** an exact-set assertion is introduced
- **THEN** a state is temporarily added, the check is observed to fail, the
  addition is reverted, and the guarded source file is shown to be byte-identical
  afterwards

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
