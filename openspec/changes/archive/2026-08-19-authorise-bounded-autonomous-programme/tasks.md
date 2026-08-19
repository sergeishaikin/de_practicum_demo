## 1. Record the supersession

- [x] 1.1 Read the two requirements in force that forbid the authorised mode of work
- [x] 1.2 Modify `Authorisation is explicit and per change` with a single named exception, and a scenario for an authorisation claimed but not recorded
- [x] 1.3 Modify `Backlog ordering is not chained authorisation` with the same exception, keeping eligibility-is-not-permission intact
- [x] 1.4 Confirm the modified requirements do not contradict each other or the rest of the capability

## 2. Bound the exception

- [x] 2.1 Add a requirement defining what a programme authorisation must state: closed membership rule, exclusions, ending conditions
- [x] 2.2 Require each item to remain its own change with its own fence, gates and archive
- [x] 2.3 Require canonical sources to be re-read before each item, with the scenario drawn from this repository's own mid-programme dependency correction
- [x] 2.4 Scenario: a failing gate is resolved in scope and never weakened to keep the programme moving
- [x] 2.5 Add a requirement that a programme never authorises its own extension, with the governance-editing failure mode called out explicitly

## 3. Gates and closure

- [x] 3.1 `openspec validate authorise-bounded-autonomous-programme --strict` and `openspec validate --specs --strict`
- [x] 3.2 Backlog validation unchanged; all fourteen `Authorised` cells still `no`
- [x] 3.3 Scope fence: no runtime, tests, CI, dependency, `.planning/` or `openspec/backlog/` change
- [x] 3.4 Documentation-only, so the Python completion gate does not apply; record that rather than implying it ran
- [x] 3.5 Commit, push, confirm live CI
- [x] 3.6 Archive, push, verify zero active changes and a clean tree
- [x] 3.7 Proceed to `add-static-typing-gate` under the now-recorded programme authorisation
