# Engineering governance

How work in this repository is planned, authorised and executed after the
2026-08-18 cutover from GSD execution to OpenSpec.

## Purpose

`.planning/` recorded a phase/plan workflow that executed Phases 1–4. That
history stays in the repository as evidence. New work is planned as OpenSpec
changes instead, so that one directory holds both the intent and the record of
what was decided, and so that a planning artifact cannot be created outside
version control.

## Requirements

### Requirement: Outstanding work is planned as an OpenSpec change

New work SHALL be proposed as a change under `openspec/changes/`, not as a new
plan under `.planning/phases/`.

#### Scenario: A defect is found by CI

- **WHEN** a repository gate fails and the cause is not yet understood
- **THEN** a change is created whose intent is to classify the failure
- **AND** runtime behaviour is not modified until the classification is
  supported by evidence

#### Scenario: A migrated obligation is picked up

- **WHEN** work that was an unexecuted `.planning/` plan is started
- **THEN** it is started as the OpenSpec change it was migrated to, and the
  original plan is not executed through GSD phase orchestration

### Requirement: `.planning/` is historical evidence, not a live queue

Completed `.planning/` artifacts SHALL remain tracked and unedited except to
record that execution was frozen. They SHALL NOT be resumed as a work queue.

#### Scenario: An unchecked plan box remains in ROADMAP.md

- **WHEN** a reader finds `- [ ] 04-08-PLAN.md` or a similar unchecked entry
- **THEN** the obligation is read from the migration mapping in
  `.planning/STATE.md`, and the work happens in the mapped OpenSpec change

### Requirement: A change states its scope fence before work starts

A change SHALL state what it is allowed to touch and what it is not, and the
fence SHALL be checkable rather than descriptive.

#### Scenario: A diagnostic change is tempted into a fix

- **WHEN** the likely remedy becomes apparent during diagnosis
- **THEN** the change does not apply it, because a diagnostic change's fence
  forbids changing behaviour before classification
- **AND** the remedy is proposed as its own change

### Requirement: Authorisation is explicit and per change

Execution of a change SHALL require the operator's explicit authorisation, and
an authorisation SHALL NOT extend to the next change.

#### Scenario: A change completes and a successor is obvious

- **WHEN** a change is finished and the next one is already written
- **THEN** work stops until the operator authorises the successor

### Requirement: A contradiction between a plan and the code stops the work

WHEN an artifact's instruction cannot be followed because the code behaves
otherwise, the work SHALL stop and report the contradiction rather than adjust
tests, expected values or prose to make the artifact appear correct.

#### Scenario: An acceptance check cannot be satisfied truthfully

- **WHEN** satisfying a stated acceptance criterion would require writing
  something untrue
- **THEN** the criterion is reported as defective, the accurate form is written,
  and the deviation is recorded in the change

### Requirement: A deferral records what would reopen it and is not a refutation

WHEN a decision defers an item rather than adopting or rejecting it, the record
SHALL state the conditions under which the item is reconsidered, and SHALL NOT
be written in a form that reads as evidence the item is unnecessary.

A deferral is a statement about the evidence available now. Recording it as a
settled conclusion transfers a certainty the evidence never carried to every
later reader, who has no way to tell the two apart from the record alone.

#### Scenario: A gate selects a no-change outcome

- **WHEN** a decision gate resolves to leaving deferred items unopened
- **THEN** the record names each deferred item, the observed evidence, and the
  conditions that would open it
- **AND** it does not state or imply that the item was found unnecessary

#### Scenario: A later reader looks up the closed decision

- **WHEN** the decision is consulted before proposing the deferred work
- **THEN** the record supplies the trigger conditions to test against, rather
  than a conclusion that forecloses the proposal
