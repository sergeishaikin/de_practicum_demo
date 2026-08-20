## Context

The failure being fixed is an inference, not a missing tool. Docker was present
and running; what was missing was a rule saying that an idle runtime is a
runtime. `AGENTS.md` said to use live markers "when their dependencies are
available" and left "available" undefined, so the cheapest reading won: if
nothing is currently listening, nothing is available.

That reading is expensive in a way that compounds. Every live check pushed to CI
is a twenty-minute round trip, and a failure there arrives as a log excerpt
rather than a debuggable process.

## Decisions

**The contract and the snapshot are separate documents, and separate halves
within one.** This is the load-bearing decision. A sentence like "Docker has
8 CPUs and 15.49 GB" is true today and false after one settings change, while
"a stopped daemon is not an unavailable dependency" is true until someone
decides otherwise. Mixing them produces a document that is partly rotten, and a
reader cannot tell which part.

So: `AGENTS.md` carries obligations. `docs/LOCAL-ENVIRONMENT.md` carries the
contract plus a snapshot explicitly labelled evidence. `DEVELOPMENT.md` carries
procedure, `TESTING.md` carries which suite needs what, and every volatile
number comes from a script.

**Nothing lists services or images by hand.** Compose can produce both
mechanically, and any transcribed copy drifts from the file it claims to
describe. That is not theoretical here: `DEVELOPMENT.md` named four locally
built images and there are six.

**The diagnostic is strictly read-only, and exits 0 when Docker is down.** Both
follow from what it is for. It is run *while deciding* whether to start
anything, in a repository that treats Docker, Kafka, Spark, MinIO, Postgres and
Iceberg as stateful — so it must be safe to run at any moment. And "Docker is
not running" is the finding, not an error: a diagnostic that fails in exactly
the state it exists to describe is useless. `--require-docker` is there for
callers that genuinely need the engine.

**It distinguishes "CLI absent" from "engine unreachable".** These are different
findings with different consequences — one is an environment limitation, the
other is a thing to fix by starting it — and collapsing them is the original
defect in miniature.

**Only `*_IMAGE` keys are read from `.env`.** The report is evidence and may be
shared, and `.env` holds passwords and JWT secrets. Restricting the parser by
construction is stronger than filtering output afterwards, because a filter has
to anticipate every key name.

**The local `.env` is reported, not corrected.** Its floating `:latest` pins for
`iceberg-rest` and `kafka-ui` mean local runs and CI runs resolve different
images, which matters for any comparison between them. But an uncommitted file
belongs to the developer, and silently rewriting it would be a worse habit than
the drift. The inventory surfaces it and `docs/LOCAL-ENVIRONMENT.md` explains
what it costs.

This also revealed the shape of the existing guard:
`test_committed_compose_pins_every_image` scans Compose, where these images are
`${VAR}` references, so it can never see this. That is correct behaviour, not a
bug — but it left `.env.example` unguarded, so a new test now asserts the
committed example pins every image by digest.

**NG-0.1's archived evidence is corrected in place, with a dated note.** Deleting
the false sentence would leave a tidy record of a thing that did not happen. The
error — treating an unexamined runtime as an absent one — is the exact failure
this change exists to prevent, and it is more useful visible than erased.

## Risks / Trade-offs

**The snapshot will go stale, and staleness looks like fact.** Mitigated by
labelling and by making regeneration one command, not by pretending otherwise.
A reader who trusts the numbers without re-running the script gets what the
label warns about.

**Contract sentences are asserted by substring.** `test_the_execution_contract_
is_actually_written_down` checks that specific phrases still appear in four
documents. That catches deletion and heading moves; it does not catch a rewrite
that keeps the phrase and reverses the meaning around it. The alternative —
asserting nothing — fails to catch the case that actually worries me, which is
the rule being quietly dropped during an unrelated edit.

**"Local first" can become "local only".** The policy says local verification
precedes clean-stack CI, not that it replaces it. CI runs on fresh volumes with
digest-pinned images and no developer state; those are properties a local run
structurally cannot have. The image-drift reporting exists partly to keep that
distinction visible.

**One machine, one snapshot.** Everything measured here describes a single
Windows host. Another developer's numbers will differ, and the contract half is
written to stay true regardless.
