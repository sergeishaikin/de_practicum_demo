## Context

The package was correct when written and became wrong by succeeding. Every
artifact encoded "fourteen items, none started", and two have since shipped.

What makes this worth a change rather than an edit is that the wrongness was
*enforced*. `validate_backlog.py` required each item file to declare itself
`PROPOSED` with `authorization NONE`, so the two completed items could not be
corrected without failing validation. A checker was holding the documentation in
a state the repository had left.

## Decisions

**State and disposition are separate columns.** Collapsing them is the obvious
simplification and it is wrong for a specific item: NG-1.3's own body says its
correct outcome may be `DO NOT IMPLEMENT`. Under a single column that experiment
would have to be recorded as unfinished or as adopted, and neither is true. A
completed experiment that concludes `DO_NOT_ADOPT` is a success, and the
register has to be able to say so.

**Authorisation records its grant, not only its date.** `Authorised: 2026-08-20`
says when and not why. Once a bounded programme authorisation exists, that
cannot distinguish "the operator authorised this item" from "this item is inside
the authorised set" — and those differ exactly where it matters, because a
programme never covers its own extension. The cell now reads
`programme:bounded-autonomous-next-generation`, with the date beside it.

**The validator checks the register against the repository.** This is the real
change. Everything the old checker verified was internal consistency: unique
ids, resolvable dependencies, topological row order. All of that can hold
perfectly while the table is simply false. `ACTIVE` is a claim that
`openspec/changes/<id>/` exists; `DONE` is a claim about the archive; both are
now checked. A `DONE` archive must also carry evidence, because an archive
missing its evidence is not a completed change.

**`STOPPED` exists even though nothing uses it.** Adding an unused state is
usually a mistake. Here the alternative is worse: without it, an abandoned item
has to be recorded as `PLANNED` — which claims the work is still ahead — or as
`DONE`, which claims it finished. The state machine is otherwise deliberately
small, because every extra state is one more thing that can disagree with the
repository.

**Item bodies are not rewritten.** The strong temptation is to update NG-0.1's
text so it describes the platform as it now is. That would destroy the record of
what was intended before implementation, which is the whole reason the file is
worth keeping, and it would quietly convert a specification into a description.
Only the header changes, and the header says which one it is.

**A `DONE` file must warn that it is historical.** The header alone is not
enough, because the failure mode is not misreading the header — it is reading
the body and finding present-tense statements about a platform that no longer
exists. NG-0.1's "the platform has useful identities and no contract binding
them" reads as a current gap. The validator requires the warning to be present,
so it cannot be dropped by an editor tidying a header.

**The directory is not moved.** `programmes/next-generation/` is the better
name; this is no longer a backlog in any useful sense. But the path is
referenced by the validator, the README, ADR-0003, `AGENTS.md`, `CLAUDE.md` and
every item cross-reference, and moving it mid-NG-0.2 spends a large diff on a
rename while the thing that actually misleads — the lifecycle — stays broken.
Semantics first; the move remains available and is cheaper once the register is
honest.

## Risks / Trade-offs

**Nine columns is a wide table.** It is at the edge of readable, and the
alternative was either dropping the file column the validator needs or folding
grant and date together, which is the ambiguity being fixed. The column contract
is written above the table so a reader does not have to infer it.

**The register still has to be edited by hand.** Nothing derives `State` from
the repository automatically — the validator only rejects disagreement. So a
completed item whose row is never updated fails validation rather than
self-correcting, which is the right failure but is still a failure someone has
to fix.

**Lifecycle is checked by directory presence.** `ACTIVE` means a directory
exists, not that work is genuinely in progress; an abandoned change directory
would keep an item looking active. `STOPPED` exists for the honest version of
that, but nothing forces its use.

**Two places record state.** The row and the file header must agree, and the
validator enforces it — but that is a consistency check, not a single source.
Storing it once would mean parsing every item file to build the register, which
trades a checkable duplication for a slower and more fragile derivation.
