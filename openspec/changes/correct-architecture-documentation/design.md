# Design: correct-architecture-documentation

## Why planes rather than one graph

The previous diagram tried to hold every container in one picture, and the
picture stopped being true as the platform grew past it. Everything in it was
once accurate; the failure was structural, not clerical — a single graph has no
way to say "this edge is core and that one is an optional development tool", so
`Airflow → Spark Connect` sat beside `Kafka → Spark Streaming` as though they
were the same kind of fact.

Six planes, each labelled with the profile that starts it, make the optionality
part of the structure. A reader can tell what runs by default without
cross-referencing the profile table, and a future optional service has an
obvious place to go that does not disturb the core picture.

## The Airflow edge, measured

Searching all five DAGs for Spark returns only `trino.dbapi.connect` and
`psycopg2.connect`. No DAG imports `pyspark`, uses an `sc://` URI, or names a
Spark service. The edge had no implementation behind it.

## The Iceberg relationship

The old diagram's `MinIO → Iceberg REST Catalog → Trino` reads as a pipeline:
data enters MinIO, passes through the catalog, arrives at Trino. What actually
happens is that the writer and Trino both consult the catalog for *metadata*
and then read and write table *data* in MinIO directly. The catalog's own state
is SQLite in a named volume and never leaves it.

The replacement draws the catalog above the participants rather than between
the stores, which is the shape of the real relationship.

## What the fitness check does and does not cover

It asserts one set equality: profiles declared across the Compose files equal
profiles named in backticks in the README's `Resource profiles` table. Both
sides are machine-readable, so the check is cheap and cannot drift into
brittleness.

Deliberately not checked: whether each row lists the right *services*, whether
the diagrams match the graph, whether the prose is current. Those are
descriptions, and turning them into snapshot assertions would produce a test
that fails on every rewording while catching nothing a reader would call a
defect. The existing `test_optional_services_have_one_resource_profile` already
pins the service-to-profile mapping for the profiles it names.

Non-vacuity was measured rather than assumed: run against the README on
`origin/main` the check reports `observability-next` and `otel` missing, and
fails.

## The one thing this change records but does not fix

`artifacts/b2-rollout/07-rollout-result.md` states the runtime finished its
observation window in the `cutover` state — `SILVER_MODE=b2`,
`GOLD_SOURCE=persisted_silver`, `SHADOW_COMPARE=1`. The committed defaults are
`legacy / legacy / 0`.

Both statements are true. One describes a live runtime during a rollout window
in August; the other describes what a fresh stack starts as today. But a reader
can reasonably take the rollout artifact as describing the current default.
That is a configuration decision — should the shipped default advance to
`cutover`? — not a documentation defect, and it is outside this change's fence.
It goes to the backlog.
