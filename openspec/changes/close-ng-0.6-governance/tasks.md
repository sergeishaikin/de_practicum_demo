# Tasks: close-ng-0.6-governance

## Authorised 2026-09-05

- [x] Verify branch, worktree, remotes and local-vs-remote `main` before any
      state-changing step.
- [x] Establish that both recorded exception branches are absent from `origin`
      by `git ls-remote`, rather than assuming the deletion happened.
- [x] Recover base branch and base SHA for every cited `pull_request` run from
      the pull requests themselves, and record the recovery method and its one
      caveat in `design.md`.
- [x] Re-anchor all seven `pull_request` citations across the four archived
      evidence files that recorded no base.
- [x] Replace NG-0.6's Class 3 placeholder with PR #14's merge-time identity:
      head, base branch and base SHA, merge commit, timestamp, the three
      workflow runs and the six required check jobs.
- [x] Record that NG-0.6's lifecycle is `DONE / ADOPTED`, so the earlier
      `ACTIVE / pending` statements are read as the state when written.
- [x] Rewrite the standing spec's **Recorded exceptions** section as history:
      there are none, with how each closed. Keep the heading — three documents
      and a fitness function point at it.
- [x] Implement the deferred evidence-shape fitness function with no exemption
      list, scoped to the section, triggered by an event label rather than the
      bare token.
- [x] Pin the false positive that the first draft produced, so the trigger
      cannot be widened back into it.
- [x] Prove the detector on the pre-change tree and record every finding.
- [x] Tick the deferred task in the archived
      `standardize-trunk-based-development` change and name where it landed, so
      no obligation stays hidden in an archived checklist.
- [x] Run the completion gate.
- [ ] Open the pull request against `main`; record head SHA, base branch, base
      SHA and every required check's run id.
- [ ] Adopt and archive this change once it has integrated.

## Explicitly out of scope

- [ ] `README.md` and architecture documentation defects. Own change.
- [ ] NG-0.7 Milestone 2 implementation. Not authorised by its own tasks.
- [ ] Branch and worktree deletion. Follows this change under the closure
      requirement, once these claims are anchored.
- [ ] Requiring every run citation to name its invocation event. Measured at
      109 citations versus 19 naming one; the rewrite is outside this fence and
      enforces a property the requirement does not state. Recorded in
      `design.md`.
