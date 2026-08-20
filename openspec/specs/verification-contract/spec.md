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

### Requirement: An installed but stopped runtime is available, not absent

A dependency whose runtime is installed on the development host SHALL be treated
as **available**. A stopped daemon, an unstarted service manager or a
not-yet-launched desktop application is a startable state, and SHALL NOT be
reported as an unavailable dependency.

When authorised work requires live services and the runtime is installed, the
runtime SHALL be started and the live check performed. A live check SHALL NOT be
skipped on the grounds that the runtime was idle when the work began.

#### Scenario: The container runtime is installed but not running

- **WHEN** a change requires live services and the container runtime is
  installed but its engine is not responding
- **THEN** the runtime SHALL be started and readiness awaited
- **AND** the live check SHALL be executed rather than deferred to CI

#### Scenario: A live check genuinely could not run

- **WHEN** a report states that a live check was not executed
- **THEN** it SHALL name what prevented it
- **AND** "the runtime was not running" SHALL NOT be accepted as that reason

### Requirement: Local live verification precedes clean-stack CI

Where the required services can run on the development host, local live
verification SHALL be performed before relying on clean-stack CI. Clean-stack CI
is independent reproducibility evidence and SHALL NOT be treated as a substitute
for a local check that could have been run.

Only the services a change requires SHOULD be started.

#### Scenario: A change could be verified locally and was not

- **WHEN** a live check is deferred to CI although the host could run it
- **THEN** the deferral SHALL be recorded with its reason, because a first
  execution in CI is a slower and less informative version of the same check

### Requirement: Environment facts are measured, not documented by hand

Claims about host or runtime capacity — CPU count, memory, service inventory,
image inventory — SHALL be produced by a repeatable read-only command rather
than transcribed into prose. Documentation SHALL separate the normative
execution contract from a dated measured snapshot, and a snapshot SHALL be
labelled as evidence rather than as a guarantee.

A resource claim about a capability profile SHALL be measured before it is made.
An assertion that the host cannot support a profile SHALL NOT rest on an
estimate when the profile could have been started and measured.

#### Scenario: A profile is declared too expensive without measurement

- **WHEN** a change concludes that the local host cannot run a capability
  profile
- **THEN** the conclusion SHALL cite measured resource figures for that profile
- **AND** an unmeasured estimate SHALL NOT stand in for them

#### Scenario: Local and CI runtimes resolve different images

- **WHEN** a local result depends on an image whose local pin differs from the
  committed pin
- **THEN** the difference SHALL be reported alongside the result
- **AND** the local result SHALL NOT be presented as equivalent to a CI result
