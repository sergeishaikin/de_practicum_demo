## Context

See proposal.md — Why. Three constraints shape the approach.

**The package is input, not output.** The fourteen specifications and their
index arrived as analysis of this branch. This change lands them; it does not
re-argue their product decisions. Where the source text was mechanically
damaged — mojibake in place of em dashes and arrows, and a dependency graph
whose box-drawing characters did not survive — the repair is typographic, and
the one graph that could not be repaired character-for-character was redrawn in
ASCII with the same edges rather than guessed at.

**A backlog is the surface with the highest risk of being misread.** Every item
is written in `SHALL` form about systems that do not exist. Two misreadings are
available to any later reader: that the file authorises the work, and that it
describes the platform. Both are cheap to make from the file alone, because
nothing inside an item's body distinguishes it from a ratified spec. The
governing requirement and the `Authorised` column exist to make both
misreadings survivable.

**Authorisation is per change and does not batch.** `engineering-governance`
already forbids one authorisation extending to the next. A backlog is precisely
a batch of future work, so it has to be recorded in a form that cannot be
cashed in as fourteen authorisations at once.

## Goals / Non-Goals

**Goals:**

- One place for recorded-but-unauthorised work, distinguishable at a glance
  from standing specs, in-flight changes and the frozen GSD record.
- The NG package landed whole and readable, with its execution order,
  dependency graph and cross-cutting invariants intact.
- A pre-assigned change id per item, so the same work cannot start twice under
  two names.
- A rule that survives the authors: the requirement, not this proposal, is what
  a later reader finds.

**Non-Goals:**

- Not evaluating the technology choices. Whether OpenMetadata beats DataHub is
  decided in NG-0.3's change, on evidence, not here.
- Not scheduling. There is no date, owner or wave ordering in the backlog.
- Not producing `tasks.md` for any item. A task list is a plan, and plans belong
  to authorised changes.
- Not starting NG-0.9 because it is small.

## Decisions

**The backlog is a sibling of `specs/` and `changes/`, not a subdirectory of
either.** Putting it under `changes/` would make it in-flight; putting it under
`specs/` would make it standing truth. Both are false about a backlog item, and
both are false in a direction that matters — one implies authorisation, the
other implies the platform already behaves this way.

**One requirement, not a family of them.** The rule needed is narrow: recorded
future work lives in the backlog, and living there authorises nothing. The
existing requirements already cover how a change is opened, fenced and
authorised, and repeating any of that in a second place would create two
statements of one rule that can drift apart.

**The change id is assigned now, not when the item is authorised.** Naming the
change in the backlog row costs nothing today and prevents a real failure later:
two people starting `NG-0.4` as `add-otel` and `add-opentelemetry-collector`
and discovering the collision after both have written a proposal.

**The `Authorised` column is a column, not a prose sentence.** Every item's body
already carries "Execution authorization: NONE" in its header. That line is easy
to skim past inside a 200-line document; a table cell that reads `no` fourteen
times in a column is not. The redundancy is deliberate — the header states it
per item, the table states it per programme.

**Baseline reconciliation notes per item were considered and rejected.** A "what
the repo has today" note inside each item dates quickly, and a stale one is worse
than none because it reads as verified. The *Freshness of external assumptions*
section is the inverse of that idea and is the one that survives: instead of
recording a snapshot that decays silently, it places an obligation on whoever
promotes the item.

**One register, not two tables.** The first draft carried a status table and an
execution-order table with overlapping columns — gate and dependencies appeared
in both. Two statements of one fact drift. They are merged into a single
register, and it is the parsed artifact, so drift becomes a check failure rather
than a discrepancy nobody notices.

**Dependencies are normalised to item ids; qualifiers move out of the column.**
The source text carried dependency prose like "0.3–0.6", "preferably 1.1" and
"and operational metadata/telemetry" — unparseable, and ambiguous about what
actually gates. The column now holds hard dependencies only, as comma-separated
ids. Soft preferences are recorded below the table where they cannot be mistaken
for gates.

**The two self-contradictions are recorded as interim readings, and neither the
governance change nor the implementing change gets to settle them.** NG-1.1's
`Dependencies` section lists "NG-0.1 through NG-0.7" — which includes NG-0.3 —
and then calls OpenMetadata "recommended before adoption". NG-1.2's dependency
sentence is weaker than its register row. Deciding either here would be deciding
an item's scope inside a governance change, which is the boundary violation the
fence exists to prevent.

The first draft handed both to the implementing change's design. That was wrong,
and it is corrected: if a governed specification disagrees with itself, letting
the implementation pick a reading retroactively rewrites what the backlog meant,
and leaves no record that the question was ever open — the implementation will
naturally choose whichever reading suits the work already done. The register
therefore carries the **stricter** reading, explicitly labelled interim, purely
so the structure stays checkable; and a fifth governance requirement makes a
discovered contradiction stop the change that finds it, to be resolved as a
bounded backlog correction or a recorded authoritative interpretation *before*
that change's design is accepted.

Stricter is the safe interim reading because over-gating can only delay work,
while under-gating can start it prematurely.

**The layering is derived, not drawn.** The first draft's ASCII graph was a
hand-made picture that could disagree with the table — and did, once the
dependency column was normalised: it showed NG-1.2 hanging off NG-1.1, which the
register says is a preference, not a dependency. The layering is now computed by
the validator from the register, and the published layering is asserted against
that computation.

**The checker is a script under `openspec/backlog/`, not a pytest test.** The
authorised fence forbids `tests/`. The repository's own idiom for a rule like
this is an `architecture`-marked fitness function beside the M5 gates, and that
is where it belongs eventually — but moving it there now would breach the fence
in the same change that argues fences are checkable rather than descriptive.
Recorded as deferred in the README and in evidence, so the gap is visible rather
than forgotten. The consequence is stated plainly: the check is executable but
not gated by CI, so today it catches a mistake only when someone runs it.

**Four governance requirements, not one.** The first draft had one. Three more
were added because a backlog introduces three distinct failure modes that no
existing requirement covers: a completed dependency reading as permission for
its dependents (the one that matters most for autonomous execution), a recorded
external premise decaying into a false fact, and a register whose invariants
live only in prose. Each is a separate rule with its own scenarios rather than
clauses bolted onto the first, because they fail independently.

## Risks / Trade-offs

**A third planning surface is a third place to look.** Mitigated by the README's
table, which names all four surfaces including `.planning/`, and by pointers in
the two files that already answer "where does planning live".

**A backlog rots.** Nothing here expires, and by NG-1.1's turn the Flink/Iceberg
compatibility line will have moved. Each item already requires re-verification
of external constraints at apply time, and the index records the baseline branch
the analysis was performed against, so a reader can tell how old the reasoning
is.

**Fourteen items may read as a commitment to fourteen products.** The index's
invariant 10 states that `DO NOT ADOPT` is a successful outcome, and five of the
items carry `EXPERIMENT` rather than `ADOPT` gates. The risk is not eliminated;
it is made visible in the same table as the items.

**The structural check is not enforced.** It exists, it has a negative proof,
and nothing runs it automatically. A register can therefore be broken and stay
broken until someone thinks to check. Accepted deliberately for one change,
because the alternative was breaching the authorised fence; the mitigation is
that the deferral is written into the README where the next reader of the
backlog will find it, not only into this change's record.

**The register is now a parsing target, which makes its format load-bearing.**
Reformatting the table — an extra column, a renamed header, a prettifier pass —
breaks the checker. That is the intended trade: the format is a contract, and
the column contracts are documented in the register itself so the constraint is
discoverable from the file being edited rather than only from the script.
