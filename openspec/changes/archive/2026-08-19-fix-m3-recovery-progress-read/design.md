## Context

See proposal.md — Why. Three constraints shape the approach.

**The root cause is already established, in this repository, with captured
bytes.** `diagnose-medallion-progress-read-corruption` settled it on 2026-08-19:
a 236-byte document returned as 521 bytes whose last 285 were heap pointers and
stray literals, while a second read and a sequential read of the same object both
returned the intact 236 bytes with an identical digest. This change does not
re-diagnose anything. It applies the settled remedy to a reader the fix missed.

**The remedy is one call, and the temptation is to add more.** The failure looks
like flakiness, and flakiness invites retries, sleeps and broader exception
handling. Every one of those would make the next green run unattributable: a race
that has been slowed down cannot be distinguished from a race that has been
removed.

**The test helper is under the same correctness contract as production.** It
polls a live object that shrinks under it. That its file lives in `tests/` says
nothing about how it must read.

## Goals / Non-Goals

**Goals:**

- Remove the stale-size mechanism from the M3 poller.
- Keep the poller fail-closed on a genuinely malformed object.
- Leave a regression that fails against both the pre-fix form and the rejected
  variant, so neither can come back quietly.

**Non-Goals:**

- Not re-establishing the root cause.
- Not auditing every `open_input_file` in the repository.
- Not touching production code — it was already fixed.
- Not starting `add-static-typing-gate`.

## Decisions

**`open_input_stream`, and nothing else.** `open_input_file` returns a random
access handle: it takes the object's length from a HEAD at open and applies that
length to a body fetched later. `open_input_stream` reads the body to EOF, so
there is no advertised size for a shrink to falsify. Same bytes, same parse, same
failure on a genuinely bad object — which is the point of choosing it over, say,
re-reading and comparing.

**The `except ValueError` I originally proposed is rejected, and the rejection is
pinned by a test.** My first proposal was to add the decode error to the retry
clause alongside the read fix, on the reasoning that the loop already tolerates
transient failure. That is wrong, and the operator's correction is adopted:

Once the read is sequential, the stale-size mechanism is gone. A `JSONDecodeError`
after that point is no longer explained by the known race — it means the stored
object really is malformed, or that some *different* concurrency behaviour
exists that has not been characterised. Absorbing it would convert either into
"wait a second, maybe it goes away", and then into a 90-second timeout reported
as `M3 work … did not complete` — the wrong diagnosis, arrived at slowly, with
the actual bytes long gone.

This is the same contract the production fix kept: `_read_json`'s own docstring
ends "same failure on a genuinely bad object". A test helper that swallowed what
production raises would be a weaker rule wearing the same fix.

Making it a decision recorded only in prose would leave nothing to stop a future
reader adding it back the next time the test flakes. So
`test_the_m3_recovery_poller_does_not_swallow_a_decode_failure` asserts the
retry clause absorbs exactly `(FileNotFoundError, OSError)` and rejects
`ValueError`, `JSONDecodeError`, `UnicodeDecodeError` and bare `Exception`. It
fails against the variant I proposed — verified, not assumed.

**No timing change of any kind.** Not the one-second poll, not the 90-second
deadline, no backoff. A race that is merely made less likely still fails, later
and less reproducibly, and any green run afterwards proves nothing about whether
the mechanism was removed. This is written into the fence so it is checkable
rather than remembered.

**The regression extends `test_progress_read_under_shrink.py` rather than
starting a new file.** That file already carries the LARGE/SMALL payloads sized
to bracket the observed 236-byte boundary, the shrinking-object fixture, and a
source assertion on the writer's reader — the exact shape needed here. A parallel
file would duplicate the fixtures and split one defect class across two homes.

**Two of the three new tests assert on source, one exercises behaviour.** For
"which API is called" and "which exceptions are absorbed", the source assertion
is the direct statement of the property, and the existing writer test set that
precedent in this file. Driving a live malformed object through a 90-second
poller to observe non-absorption would take 90 seconds to prove the same thing.
The third test — a malformed object must still raise — is behavioural, because
that one is about what the reader *does*, not what it says.

**`tests/support/progress_read_diagnostics.py` keeps its `open_input_file`.** It
is the module that reproduces and captures the random-access read as evidence.
Changing it would delete the instrument that produced the diagnosis. Recorded
here because a future reader grepping for the defective call will find it and
needs to know it is deliberate.

## Risks / Trade-offs

**Three green H1 runs do not prove a race is gone.** They raise confidence and
they are the agreed acceptance bar, but the honest claim is bounded: the
mechanism that explains the observed failure has been removed from the reader,
and three subsequent runs on one SHA did not reproduce it. That is what the
evidence supports, and the evidence file says exactly that rather than "fixed".

**A source assertion can be satisfied without the behaviour being right.**
Someone could reintroduce a random-access read through a differently named local,
or absorb the decode error further out. The mitigation is partial: the
behavioural malformed-object test covers the reader itself, and the fence forbids
the specific edits. A test that reads source is a tripwire, not a proof.

**The failure may have more than one cause.** One occurrence in three runs is a
small sample, and only the stale-size mechanism is addressed. If it recurs after
this change, the correct response is to capture the bytes and classify — not to
add the retry that was rejected here. That instruction is in the evidence file
where the next person to see a red H1 will look.
