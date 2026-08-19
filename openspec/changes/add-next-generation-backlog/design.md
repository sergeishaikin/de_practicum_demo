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

**The index gains a status table; the item bodies are unchanged.** The approved
breakdown was the status/authorisation table only. Baseline reconciliation notes
per item — what the repo already has against each gap — were considered and not
added: they date quickly, and an out-of-date "what exists today" note inside a
backlog item is worse than no note, because it reads as verified.

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
invariant 10 states that `DO NOT ADOPT` is a successful outcome, and four of the
items carry `EXPERIMENT` rather than `ADOPT` gates. The risk is not eliminated;
it is made visible in the same table as the items.
