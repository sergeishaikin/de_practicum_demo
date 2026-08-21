## ADDED Requirements

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
