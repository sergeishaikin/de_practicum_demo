## 1. Audit

- [x] 1.1 Read all fourteen item files, the register, the README and the validator
- [x] 1.2 Establish actual state from `openspec/changes/` and `openspec/changes/archive/`
- [x] 1.3 Confirm NG-0.9 and NG-0.1 resolve to complete archives
- [x] 1.4 Confirm NG-0.2 resolves to an active change
- [x] 1.5 Record the three concrete inconsistencies: unrepresentable lifecycle, a validator enforcing a false invariant, and two governance documents describing different operating models

## 2. Register

- [x] 2.1 Separate `Gate`, `State`, `Disposition`, `Authorised by` and `At`
- [x] 2.2 Set NG-0.9 and NG-0.1 to `DONE` / `ADOPTED`
- [x] 2.3 Set NG-0.2 to `ACTIVE` / `pending`
- [x] 2.4 Leave the remaining eleven `PLANNED` / `pending` / unauthorised
- [x] 2.5 Record authorisation provenance rather than a bare date
- [x] 2.6 Rewrite the column contract and the row-editing rule to match
- [x] 2.7 State that a completed item is historical intent, not current truth

## 3. Item files

- [x] 3.1 Replace only the header block on all fourteen; leave every technical body untouched
- [x] 3.2 `DONE` headers name the implementing change and its archive
- [x] 3.3 `DONE` headers warn that the body is historical intent
- [x] 3.4 `ACTIVE` header names the change in flight and its grant
- [x] 3.5 `PLANNED` headers keep the explicit no-authorisation statement

## 4. Validator

- [x] 4.1 Parse the new columns; validate states and dispositions against their allowed sets
- [x] 4.2 State and disposition agree — no `DONE` with `pending`, no `PLANNED` with an outcome
- [x] 4.3 Authorisation is traceable and dated; nothing started is unauthorised
- [x] 4.4 Check lifecycle against `openspec/changes/` and `openspec/changes/archive/`
- [x] 4.5 A `DONE` archive carries proposal, design, tasks and evidence
- [x] 4.6 No item is `ACTIVE` or `DONE` while a hard dependency is `PLANNED`
- [x] 4.7 Each item file's header matches its row
- [x] 4.8 Remove the false `PROPOSED` / `NONE` invariant, keeping the freshness marker

## 5. Tests

- [x] 5.1 A truthful register passes, so the negative cases mean something
- [x] 5.2 `DONE` without an archive
- [x] 5.3 `DONE` with an incomplete archive
- [x] 5.4 `ACTIVE` without an active change
- [x] 5.5 `PLANNED` with implementation under way
- [x] 5.6 A dependent item running before its prerequisite
- [x] 5.7 An item file disagreeing with its row
- [x] 5.8 Authorisation without a traceable grant
- [x] 5.9 A completed experiment may conclude `DO_NOT_ADOPT`
- [x] 5.10 A `DONE` item must carry the historical-intent warning
- [x] 5.11 The live register checked against the live repository
- [x] 5.12 Wire the checker into the fast suite, which it never was

## 6. README

- [x] 6.1 Record bounded-programme authorisation alongside per-item authorisation
- [x] 6.2 Describe the lifecycle and the promotion contract in its terms
- [x] 6.3 State that a completed item is historical intent
- [x] 6.4 Describe what the validator now checks, and that it is gated

## 7. Closure

- [x] 7.1 ruff, black, mypy, pytest with the coverage gate
- [x] 7.2 Backlog validation green against the real repository
- [x] 7.3 Scope fence — no item body, no production code
- [ ] 7.4 Commit, push, confirm live CI
- [ ] 7.5 Evidence, archive, push
- [ ] 7.6 Resume NG-0.2 without further authorisation
