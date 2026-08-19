# Evidence — add-next-generation-backlog

Executed 2026-08-19 on `test/dbt-extensive-testing` at `2d78eb9`.

## What landed

| Path | Files |
|---|---|
| `openspec/backlog/README.md` | 1 |
| `openspec/backlog/next-generation/` | 15 (`00-INDEX.md` + NG-0.1 … NG-2.2) |
| `openspec/changes/add-next-generation-backlog/` | 5 + spec delta |
| `AGENTS.md`, `CLAUDE.md` | 1 pointer each |

## Checks executed

| Check | Command | Result |
|---|---|---|
| Change validity | `openspec validate add-next-generation-backlog --strict` | `Change 'add-next-generation-backlog' is valid` |
| Standing specs still valid | `openspec validate --specs --strict` | 2 passed, 0 failed (`engineering-governance`, `verification-contract`) |
| Scope fence | `git status --porcelain` | Only `M AGENTS.md`, `M CLAUDE.md`, and the two new untracked directories. No modification under `iceberg/`, `dags/`, `dbt/`, `spark/`, `kafka/`, `observability/`, `tests/`, `scripts/`, `.planning/`; no Compose, `pyproject.toml`, lock or CI workflow edit |
| Encoding | `iconv -f UTF-8 -t UTF-8` over all 21 new files | All valid UTF-8 |
| Mojibake | `grep -rl 'â'` over the new files | No match |
| Item headers | `grep -c 'Status:\*\* PROPOSED'` and `grep -c 'Execution authorization'` | 1 each in all 15 backlog files |
| Authorisation column | `grep -c '\| no \|' 00-INDEX.md` | 14 — every item unauthorised |
| Change-id uniqueness | `grep -oE` over the index, `sort \| uniq -c` | 14 ids, each occurring once |
| Backlog is tracked | `git check-ignore -v openspec/backlog/README.md` | Not ignored |

## Checks not executed, and why

- **Python completion gate** (`ruff`, `black`, `pytest`, coverage). Not run. This
  change is documentation and planning only; no Python file, executable command
  or configuration example is touched, which is the exemption `AGENTS.md` states.
- **Live stack, integration, E2E, M5/H1/S1 gates.** Not run and not applicable.
  No runtime surface is involved.

## Observations

- **markdownlint defaults flag these files, and flag the archived changes
  equally.** An ad-hoc `markdownlint-cli2` run with *default* rules reports
  MD013 (80-column) and MD041 (first line must be H1) across the new files.
  Running the same command against the accepted, archived
  `2026-08-19-define-steady-state-shadow-policy` produces the same classes of
  finding. The repository's `.trunk/trunk.yaml` enables `markdownlint@0.49.1`
  but ships no markdownlint config, and none of the six CI workflows runs trunk.
  The new files therefore match the house style of the existing changes; the
  findings describe a default rule set the repository does not apply to this
  surface, not a regression introduced here.

- **The source package arrived mechanically damaged.** Em dashes and arrows had
  been transcoded to `â` sequences throughout, and the index's dependency graph
  had lost its box-drawing characters. The dashes and arrows were repaired by
  context. The graph could not be repaired character-for-character with
  confidence, so it was redrawn in ASCII carrying the same edges — the substitution
  is visible in the diff and is recorded here rather than presented as a faithful
  transcription.

- **NG-0.9's premise was checked against this branch and holds.**
  `pyproject.toml` pins `black==25.9.0`, `ruff==0.12.0`, `sqlfluff==3.4.2` and
  `pytest==8.4.2` in the dev group, and no type checker. A stray `.mypy_cache/`
  exists at both repository levels from an ad-hoc invocation; it is not a
  configured or enforced gate. The other thirteen items' premises were **not**
  re-verified against the codebase — verifying a gap is work that belongs to
  each item's own change, and doing it here would have produced dated claims
  inside documents that will be read months from now.

## Deliberately not done

- No backlog item is authorised. All fourteen `Authorised` cells read `no`.
- No item was copied into `openspec/changes/` as a proposal.
- NG-0.9 was not started, despite being the cheapest of the fourteen.
- `.planning/` was not edited. The open `04-09` / BENCH-01 obligation recorded
  there is untouched and remains unauthorised.
