# Proposal: close-ng-0.6-governance

## Problem

NG-0.6 integrated on 2026-09-04 as PR #14, but its governance did not close
with it. Three artifacts still describe a state that no longer exists.

- The standing `development-workflow` capability's **Recorded exceptions**
  table claims `feature/ng-0.6-loki` and `test/dbt-extensive-testing` are
  deliberately retained. Both are absent from `origin`. A spec that describes
  the repository as it is not is worse than one that is silent: it is read as
  authority.
- NG-0.6's archived evidence closes with a placeholder — "Recorded from the
  pull request; see the table below once the final head is known" — where the
  merge-time authority should be. The change that motivated the entire
  `development-workflow` capability therefore records no receipt for its own
  integration.
- `standardize-trunk-based-development` deferred the evidence-shape fitness
  function with an explicit reason: the only non-conforming file was the one
  the rule was written for, and it was frozen, so a checker written then would
  have needed an exemption for exactly that file. That blocker is gone.

Seven `pull_request` citations across four archived evidence files record no
base at all. Each is green and each is genuine; none of them lets a reader see
what was actually merged, which is the property the capability requires.

## Proposed bounded change

Close NG-0.6's governance and land the deferred checker.

Re-anchor every `pull_request` citation in the archive to base branch and base
SHA, recovered from the pull requests themselves rather than inferred. Replace
the NG-0.6 placeholder with PR #14's merge-time identity. Rewrite **Recorded
exceptions** as history, stating that there are none and how each closed.
Implement the evidence-shape fitness function with no exemption list, and
validate every archived evidence file against it.

## Non-goals

- No change to what any receipt claims. Re-anchoring adds the base that was
  always true of a run; it does not restate a conclusion, upgrade a historical
  receipt into adoption evidence, or alter a single run id or conclusion.
- No new requirement. The evidence-shape rule already exists as **An adoption
  receipt proves the candidate against its real integration base**; this change
  makes it executable.
- No deletion of the **Recorded exceptions** heading. Three documents and one
  fitness function point at it, and a reader of an older receipt needs to find
  what the branches were.

## Scope fence

- This change SHALL NOT modify `README.md` or the architecture documentation.
  Those defects are real and are closed by their own change.
- This change SHALL NOT implement NG-0.7. Its branch carries M1 research only,
  and its own tasks record that M2 is not authorised.
- This change SHALL NOT delete any branch. Cleanup follows, under the closure
  requirement, once this change's claims are anchored.
- This change SHALL NOT require every run citation to name its invocation
  event. The corpus holds 109 run citations and only 19 name one; rewriting the
  other 90 would be a wholesale rewrite of historical evidence, far outside
  this fence, for a property the requirement does not ask for. The residual is
  recorded in `design.md`.
