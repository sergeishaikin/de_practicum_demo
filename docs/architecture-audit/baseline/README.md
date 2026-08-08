# Architecture audit baseline

This directory holds the **final, frozen output** of the architecture audit that produced
[ADR-0001](../../adr/0001-incremental-silver-and-gold.md). It is project documentation, not tool
state.

## What is here, and what is deliberately not

| | |
|---|---|
| **Committed here** | The synthesis phase only — findings, verdict, coverage, and what was rejected or deferred. |
| **Not committed** | Intermediate audit-kit artifacts (inventory, intent profile, per-specialist findings, workflow state). They live locally under `.architecture-audit/`, excluded via `.git/info/exclude`. |

The boundary is intentional:

```
ADR-0001            = the decision and its argument     (self-sufficient)
baseline/synthesis  = the full evidence and audit trail (this directory)
.architecture-audit = local working state               (not shared)
```

**ADR-0001 is readable and checkable without this directory.** Every claim it makes carries a
`file:line` reference into the repository itself. This baseline exists for a different purpose:
it is the immutable reference a later `verify-architecture-remediation` run compares against.

## Contents

| File | Purpose |
|---|---|
| `synthesis/synthesis.md` | The verdict: five root causes, four decisions, one prerequisite, adversarial challenge, strengths |
| `synthesis/architecture-findings.json` | All 28 findings with full evidence chains, plus the decision structure. Schema `architecture-audit-report.v1` |
| `synthesis/rejected-or-deferred-findings.md` | What the challenge pass changed, what was deferred and why, and what would overturn the synthesis |
| `synthesis/coverage.md` | Scope, phases run and skipped, method, and everything that was **not** observed |

## Digests

Recorded so this baseline can be shown to be unmodified. Verify with `sha256sum`.

| File | sha256 |
|---|---|
| `synthesis/architecture-findings.json` | `8417535f73fc2a3405c1e99aa8fd0191a07ea44edca3dea60d7e9bf84a0faf3b` |
| `synthesis/synthesis.md` | `b896fb5540f49957c0f2f4142c2003db9f4d666a07b2bc9cf51118370c356387` |
| `synthesis/rejected-or-deferred-findings.md` | `9d47c9751de6986662213796ea4c9a5b9fbf9048d3305fe0de92c89384f59f8f` |
| `synthesis/coverage.md` | `628c1dd9dd13e053722d696267a3e3fb06ef5c39222e0eb43622aad83567a58a` |

The `inputs` block inside `architecture-findings.json` also records digests of the four
intermediate artifacts that fed synthesis. Those files are not committed; the digests are kept so
that a regenerated inventory or profile can be checked for drift against what this audit actually
saw.

## Rules for this directory

1. **Immutable.** Do not edit these files. A later audit produces a *new* baseline; it does not
   amend this one.
2. **Read `coverage.md` before comparing anything.** The audit was deliberately narrow — five
   specialist reviews were not run. If a later audit's scope differs materially, the comparison is
   `INCOMPARABLE`, not an improvement or a regression.
3. **Do not cite `riskIndex`.** It is 100.0, saturated, and meaningless as a grade. `coverage.md`
   explains why.
4. **No conformance score exists.** It is suppressed because the repository had zero ADRs at
   capture time — ADR-0001 is the first.

## Regenerating

The audit ran on revision `d20b2062`. To re-run it, the exclusion set in `coverage.md` must be
passed on every invocation: `--exclude` augments the scanner's defaults rather than replacing
them, and is not persisted between runs.
