from __future__ import annotations

import json
from datetime import date, datetime
from types import SimpleNamespace

import pyarrow as pa
import pytest

from medallion import iceberg_medallion as m
from tests.support.b2_fakes import FakeFS
from tests.support.fakes import FakeCatalog as SharedFakeCatalog
from tests.support.fakes import FakeMetrics, scripted_monotonic

TS = datetime(2026, 1, 1, 12, 0, 0)


def row(order_id: str, version: int, *, amount: float = 10.0, offset: int = 1) -> dict:
    return {
        "order_id": order_id,
        "customer": f"customer-{order_id}",
        "amount": amount,
        "country": "US",
        "status": "paid",
        "event_time": TS,
        "kafka_timestamp": TS,
        "kafka_partition": 0,
        "kafka_offset": offset,
        "event_date": date(2026, 1, 1),
        "business_version": version,
    }


def table(rows: list[dict]) -> pa.Table:
    return m._rows_to_silver(rows)


def test_shadow_comparison_is_order_and_transport_independent() -> None:
    legacy = table([row("b", 2, offset=1), row("a", 1, offset=2)])
    b2 = table([row("a", 1, offset=999), row("b", 2, offset=888)])
    result = m.compare_business_state(legacy, b2)
    assert result["equal"]
    assert result["excluded_columns"] == [
        "kafka_timestamp",
        "kafka_partition",
        "kafka_offset",
    ]


def test_every_silver_column_is_classified_for_shadow_comparison() -> None:
    """Every Silver column is either business state or declared transport.

    `compare_business_state` iterates `SHADOW_BUSINESS_COLUMNS` and ignores
    everything else, so a column added to `SILVER_SCHEMA` and registered in
    neither tuple would silently drop out of business-state equality instead of
    failing. This pins the classification as a total, disjoint partition.
    """

    silver_columns = {field.name for field in m.SILVER_SCHEMA.fields} - {"order_id"}
    business = set(m.SHADOW_BUSINESS_COLUMNS)
    excluded = set(m.SHADOW_EXCLUDED_COLUMNS)

    assert silver_columns == business | excluded
    assert not business & excluded


def test_shadow_duplicate_resolution_is_independent_of_physical_row_order() -> None:
    first = table([row("a", 2, amount=20), row("a", 1, amount=10)])
    second = table([row("a", 1, amount=10), row("a", 2, amount=20)])

    result_first = m.compare_business_state(first, table([row("a", 1, amount=10)]))
    result_second = m.compare_business_state(second, table([row("a", 1, amount=10)]))

    assert result_first == result_second
    assert result_first["mismatches"][0]["mismatch_type"] == "duplicate_business_key"


@pytest.mark.parametrize(
    ("legacy", "b2", "mismatch_type"),
    [
        ([row("a", 1)], [row("b", 1)], "missing_in_persisted_b2"),
        ([row("b", 1)], [row("a", 1), row("b", 1)], "missing_in_legacy"),
        ([row("a", 1), row("a", 1)], [row("a", 1)], "duplicate_business_key"),
        ([row("a", 1)], [row("a", 2)], "business_version_mismatch"),
        ([row("a", 1, amount=10)], [row("a", 1, amount=11)], "payload_mismatch"),
    ],
)
def test_shadow_comparison_reports_deterministic_mismatch(
    legacy: list[dict], b2: list[dict], mismatch_type: str
) -> None:
    result = m.compare_business_state(table(legacy), table(b2))
    assert not result["equal"]
    assert result["mismatches"][0]["mismatch_type"] == mismatch_type
    assert result["mismatches"][0]["order_id"] == "a"


class FakeTable:
    """Local double, mirroring ``tests/support/fakes.py:FakeTable`` field-for-field.

    Kept separate deliberately rather than reusing the shared double: that one's
    ``scan()`` yields ``None`` for an empty table, while several Gold tests in
    this module depend on an empty *typed* Arrow table instead. Converging them
    would mean changing the shared double's empty-scan semantics for every other
    consumer, so the duplication is a decision, not an oversight.
    """

    def __init__(self, arrow_table: pa.Table | None = None) -> None:
        self.df = arrow_table
        self.overwrite_calls = 0
        self.snapshots: list = []
        self.snapshot_properties: list[dict] = []

    def scan(self, row_filter=None):
        return SimpleNamespace(
            to_arrow=lambda: self.df if self.df is not None else table([])
        )

    def add_snapshot(self, **summary):
        snapshot = SimpleNamespace(
            snapshot_id=len(self.snapshots) + 1,
            summary=SimpleNamespace(additional_properties=dict(summary)),
        )
        self.snapshots.append(snapshot)
        return snapshot

    def current_snapshot(self):
        return self.snapshots[-1] if self.snapshots else None

    def overwrite(self, arrow_table, **kwargs) -> None:
        self.df = arrow_table
        self.overwrite_calls += 1
        properties = dict(kwargs.get("snapshot_properties") or {})
        self.snapshot_properties.append(properties)
        self.add_snapshot(**properties)


class FakeCatalog:
    def __init__(self, tables: dict[str, FakeTable]) -> None:
        self.tables = tables

    def load_table(self, identifier: str) -> FakeTable:
        return self.tables[identifier]


def setup_gold_run(monkeypatch, *, gold_source: str, shadow: bool = False):
    bronze = FakeTable(table([row("a", 1)]))
    persisted_silver = FakeTable(table([row("a", 5, amount=50)]))
    gold = FakeTable()
    catalog = FakeCatalog(
        {
            "bronze.orders": bronze,
            "silver.orders_clean": persisted_silver,
            "gold.orders_daily_metrics": gold,
        }
    )
    monkeypatch.setattr(m, "ensure_table", lambda *args: None)
    # Keyword-tolerant: plan 04-03 calls run_b2(..., cycle_id=...), and a bare
    # *args lambda raises TypeError on any keyword argument.
    monkeypatch.setattr(m, "run_b2", lambda *args, **kwargs: None)
    monkeypatch.setattr(m, "GOLD_SOURCE", gold_source)
    monkeypatch.setattr(m, "SHADOW_COMPARE_ENABLED", shadow)
    return catalog, persisted_silver, gold, FakeMetrics()


def test_cutover_gold_is_served_from_persisted_silver(monkeypatch) -> None:
    # Scoped to the accepted cutover state (b2 / persisted_silver / shadow on),
    # which is the only accepted configuration that reads persisted Silver.
    #
    # Shadow validation needs the legacy projection, so a rebuild *does* happen
    # here — an earlier version of this test asserted the opposite, but reached
    # that state with shadow off, a combination the rollout matrix forbids and
    # main() refuses to boot into. What the cutover contract actually requires is
    # that Gold is fed from persisted Silver rather than from the rebuild, and
    # that the Gold cycle never rewrites persisted Silver.
    catalog, persisted_silver, gold, metrics = setup_gold_run(
        monkeypatch, gold_source="persisted_silver", shadow=True
    )
    persisted_silver.df = table([row("a", 1)])

    gold_inputs = []
    real_build_gold = m.build_gold

    def capture_gold_input(df):
        gold_inputs.append(df)
        return real_build_gold(df)

    monkeypatch.setattr(m, "build_gold", capture_gold_input)

    m.run(catalog, metrics, "b2")

    # Identity, not equality: shadow compare forces the two projections to agree,
    # so only object identity can tell which one reached Gold.
    assert gold_inputs, "Gold was never built"
    assert gold_inputs[0] is persisted_silver.df
    assert gold.df is not None
    assert gold.overwrite_calls == 1
    assert persisted_silver.overwrite_calls == 0
    assert metrics.records[-1]["status"] == "success"
    assert metrics.records[-1]["shadow_comparisons"] == 1


def test_shadow_mismatch_fails_closed_before_gold_write(monkeypatch) -> None:
    catalog, _, gold, metrics = setup_gold_run(
        monkeypatch, gold_source="legacy", shadow=True
    )
    with pytest.raises(ValueError, match="Shadow comparison failed"):
        m.run(catalog, metrics, "b2")
    assert gold.overwrite_calls == 0
    assert metrics.records[-1]["status"] == "shadow_failed"
    assert metrics.records[-1]["shadow_comparisons"] == 1
    assert metrics.records[-1]["shadow_mismatches"] == 1


def test_shadow_uses_bronze_boundary_pinned_before_b2_runs(monkeypatch) -> None:
    catalog, persisted_silver, gold, metrics = setup_gold_run(
        monkeypatch, gold_source="legacy", shadow=True
    )
    persisted_silver.df = table([row("a", 1)])

    def mutate_bronze_after_boundary(*args, **kwargs) -> None:
        catalog.tables["bronze.orders"].df = table([row("a", 2)])

    monkeypatch.setattr(m, "run_b2", mutate_bronze_after_boundary)

    m.run(catalog, metrics, "b2")

    assert gold.overwrite_calls == 1
    assert metrics.records[-1]["status"] == "success"


def test_switching_gold_source_does_not_mutate_persisted_silver(monkeypatch) -> None:
    catalog, persisted_silver, gold, metrics = setup_gold_run(
        monkeypatch, gold_source="persisted_silver"
    )
    m.run(catalog, metrics, "b2")
    persisted_snapshot = persisted_silver.overwrite_calls

    monkeypatch.setattr(m, "GOLD_SOURCE", "legacy")
    monkeypatch.setattr(m, "SHADOW_COMPARE_ENABLED", False)
    m.run(catalog, metrics, "b2")

    assert persisted_silver.overwrite_calls == persisted_snapshot
    assert gold.overwrite_calls == 2


def test_fake_table_records_snapshot_properties_and_advances_current() -> None:
    """The double must express what a Gold write carried and which snapshot won."""

    gold = FakeTable()
    gold.overwrite(table([]), snapshot_properties={"source-silver-snapshot-id": "11"})
    gold.overwrite(table([]), snapshot_properties={"source-silver-snapshot-id": "22"})

    assert gold.current_snapshot().snapshot_id == 2
    assert len(gold.snapshot_properties) == 2
    assert gold.snapshot_properties[-1] == {"source-silver-snapshot-id": "22"}


def test_fake_table_current_snapshot_ignores_older_provenance() -> None:
    """A bare newer snapshot must hide an older property-bearing one.

    This is the fixture the "read provenance from current_snapshot() only" rule
    needs: a Trino maintenance rewrite can leave a newer snapshot with no
    provenance property, and trusting an older one would silently certify Gold
    against a Silver snapshot that no longer produced it.
    """

    gold = FakeTable()
    gold.add_snapshot(**{"source-silver-snapshot-id": "11"})
    gold.add_snapshot()

    assert gold.current_snapshot().summary.additional_properties == {}


# --- MTL-01: cycle identity, phase records, non-overlapping durations ---------


def b2_stub(*, duration_ms: int = 3000, silver_snapshot_id: int | None = 4242):
    """A ``run_b2`` replacement that emits its own phase record, as the real one does.

    The stubs used elsewhere in this module return ``None`` to mean "no physical
    cost measured"; this one stands in for a B2 pass that actually did work, so a
    test can assert on the four-record shape.
    """

    def _run_b2(catalog, metrics, fs=None, *, cycle_id=None):
        metrics.record(
            source="medallion",
            status="success",
            phase="b2",
            cycle_id=cycle_id,
            silver_rows=1,
            duration_ms=duration_ms,
            silver_snapshot_id=silver_snapshot_id,
            files_planned=7,
            bytes_planned=700,
            keys_processed=3,
            work_in_flight=0,
        )
        return m.B2Outcome(
            duration_ms=duration_ms,
            silver_rows=1,
            files_processed=1,
            keys_processed=3,
            lower_versions_ignored=0,
            ff14_conflicts=0,
            work_available=0,
            work_in_flight=0,
            work_completed=1,
            files_planned=7,
            bytes_planned=700,
            files_removed=1,
            files_added=2,
            bytes_removed=100,
            bytes_added=200,
            snapshot_delta=1,
            silver_snapshot_id=silver_snapshot_id,
        )

    return _run_b2


def test_one_cycle_emits_one_record_per_phase(monkeypatch) -> None:
    catalog, persisted_silver, _gold, metrics = setup_gold_run(
        monkeypatch, gold_source="persisted_silver", shadow=True
    )
    persisted_silver.df = table([row("a", 1)])
    monkeypatch.setattr(m, "run_b2", b2_stub())

    m.run(catalog, metrics, "b2")

    assert len(metrics.records) == 4
    assert {r["phase"] for r in metrics.records} == {"b2", "shadow", "gold", "cycle"}


def test_every_record_in_one_cycle_shares_one_cycle_id(monkeypatch) -> None:
    catalog, persisted_silver, _gold, metrics = setup_gold_run(
        monkeypatch, gold_source="persisted_silver", shadow=True
    )
    persisted_silver.df = table([row("a", 1)])
    monkeypatch.setattr(m, "run_b2", b2_stub())

    m.run(catalog, metrics, "b2")

    cycle_ids = {r["cycle_id"] for r in metrics.records}
    assert len(cycle_ids) == 1
    assert cycle_ids.pop()


def test_the_cycle_record_is_written_last(monkeypatch) -> None:
    """The exporter's ``distinct on (source)`` must keep resolving to cycle state."""

    catalog, persisted_silver, _gold, metrics = setup_gold_run(
        monkeypatch, gold_source="persisted_silver", shadow=True
    )
    persisted_silver.df = table([row("a", 1)])
    monkeypatch.setattr(m, "run_b2", b2_stub())

    m.run(catalog, metrics, "b2")

    assert metrics.records[-1]["phase"] == "cycle"


def test_phase_durations_are_disjoint_and_bounded_by_the_cycle(monkeypatch) -> None:
    catalog, persisted_silver, _gold, metrics = setup_gold_run(
        monkeypatch, gold_source="persisted_silver", shadow=True
    )
    persisted_silver.df = table([row("a", 1)])
    monkeypatch.setattr(m, "run_b2", b2_stub(duration_ms=3000))
    # t0=0  b2=[1,4]  gold_start=10  t3=16
    monkeypatch.setattr(m.time, "monotonic", scripted_monotonic([0, 1, 4, 10, 16]))

    m.run(catalog, metrics, "b2")

    b2 = metrics.phase("b2")["duration_ms"]
    shadow = metrics.phase("shadow")["duration_ms"]
    gold = metrics.phase("gold")["duration_ms"]
    cycle = metrics.cycle()["duration_ms"]

    assert b2 == 3000
    # the whole pre-Gold segment (10s) minus the incremental writer's window (3s)
    assert shadow == 7000
    assert gold == 6000
    assert cycle == 16000
    assert cycle >= b2 + shadow + gold


def test_inclusive_durations_stay_on_the_cycle_record_only(monkeypatch) -> None:
    catalog, persisted_silver, _gold, metrics = setup_gold_run(
        monkeypatch, gold_source="persisted_silver", shadow=True
    )
    persisted_silver.df = table([row("a", 1)])
    monkeypatch.setattr(m, "run_b2", b2_stub())
    # Scripted, not wall-clock: a sub-millisecond fake run would round the
    # inclusive durations to zero and make the positive assertion vacuous.
    monkeypatch.setattr(m.time, "monotonic", scripted_monotonic([0, 1, 4, 10, 16]))

    m.run(catalog, metrics, "b2")

    for record in metrics.records:
        if record["phase"] == "cycle":
            continue
        assert not record.get("silver_duration_ms")
        assert not record.get("gold_duration_ms")

    cycle = metrics.cycle()
    assert cycle["silver_duration_ms"] == 10000
    assert cycle["gold_duration_ms"] == 6000


def test_shadow_failure_is_recorded_as_an_aborted_cycle(monkeypatch) -> None:
    catalog, persisted_silver, gold, metrics = setup_gold_run(
        monkeypatch, gold_source="legacy", shadow=True
    )
    persisted_silver.df = table([row("a", 9, amount=99)])
    monkeypatch.setattr(m, "run_b2", b2_stub())

    with pytest.raises(ValueError):
        m.run(catalog, metrics, "b2")

    aborted = metrics.cycle()
    assert aborted["status"] == "shadow_failed"
    assert gold.overwrite_calls == 0


def test_a_b2_stub_returning_none_still_yields_a_zeroed_cycle(monkeypatch) -> None:
    """`None` means "no physical cost measured", never a crashed cycle."""

    catalog, persisted_silver, gold, metrics = setup_gold_run(
        monkeypatch, gold_source="persisted_silver", shadow=True
    )
    persisted_silver.df = table([row("a", 1)])

    m.run(catalog, metrics, "b2")

    cycle = metrics.cycle()
    assert gold.overwrite_calls == 1
    assert cycle["status"] == "success"
    assert cycle["files_planned"] == 0
    assert cycle["bytes_planned"] == 0
    assert cycle["keys_processed"] == 0
    assert cycle["work_in_flight"] == 0
    assert {r["phase"] for r in metrics.records} == {"shadow", "gold", "cycle"}


def test_snapshot_identities_are_recorded_where_they_are_meaningful(
    monkeypatch,
) -> None:
    catalog, persisted_silver, _gold, metrics = setup_gold_run(
        monkeypatch, gold_source="persisted_silver", shadow=True
    )
    persisted_silver.df = table([row("a", 1)])
    monkeypatch.setattr(m, "run_b2", b2_stub(silver_snapshot_id=4242))

    m.run(catalog, metrics, "b2")

    assert metrics.phase("b2")["silver_snapshot_id"] == 4242
    assert "bronze_snapshot_id" in metrics.phase("shadow")
    assert "gold_snapshot_id" in metrics.phase("gold")
    cycle = metrics.cycle()
    assert {"bronze_snapshot_id", "silver_snapshot_id", "gold_snapshot_id"} <= set(
        cycle
    )


# --- GLD-01: Gold provenance and the elided rebuild --------------------------
#
# The double's snapshot ids are small integers, so a test that wants "Silver
# moved" says `add_snapshot()` and a test that wants "Silver has never been
# committed" simply says nothing. `setup_gold_run` deliberately leaves the Silver
# double snapshotless, which is why the four pre-existing Gold contracts above
# still write Gold on every run: a `None` snapshot id can never certify anything.


def test_unchanged_persisted_silver_skips_the_gold_rebuild(monkeypatch, capsys) -> None:
    """GLD-01a: a second cycle over an unmoved Silver snapshot writes no Gold."""

    catalog, persisted_silver, gold, metrics = setup_gold_run(
        monkeypatch, gold_source="persisted_silver", shadow=True
    )
    persisted_silver.df = table([row("a", 1)])
    persisted_silver.add_snapshot()

    m.run(catalog, metrics, "b2")
    second = FakeMetrics()
    m.run(catalog, second, "b2")

    assert gold.overwrite_calls == 1
    assert metrics.phase("gold")["gold_skipped"] is False
    assert second.phase("gold")["gold_skipped"] is True
    assert second.cycle()["gold_skipped"] is True
    # A skip must never be indistinguishable from a write in the evidence.
    assert "gold=skipped" in capsys.readouterr().out


def test_a_moved_silver_snapshot_rebuilds_gold(monkeypatch) -> None:
    """GLD-01b: any persisted Silver change rebuilds Gold."""

    catalog, persisted_silver, gold, metrics = setup_gold_run(
        monkeypatch, gold_source="persisted_silver", shadow=True
    )
    persisted_silver.df = table([row("a", 1)])
    persisted_silver.add_snapshot()

    m.run(catalog, metrics, "b2")
    persisted_silver.add_snapshot()
    second = FakeMetrics()
    m.run(catalog, second, "b2")

    assert gold.overwrite_calls == 2
    assert metrics.phase("gold")["gold_skipped"] is False
    assert second.phase("gold")["gold_skipped"] is False


def test_a_gold_write_stamps_the_silver_snapshot_it_was_built_from(monkeypatch) -> None:
    """GLD-01c: the provenance the next cycle reads is written by this one."""

    catalog, persisted_silver, gold, metrics = setup_gold_run(
        monkeypatch, gold_source="persisted_silver", shadow=True
    )
    persisted_silver.df = table([row("a", 1)])
    persisted_silver.add_snapshot()

    m.run(catalog, metrics, "b2")

    silver_snapshot_id = persisted_silver.current_snapshot().snapshot_id
    assert gold.snapshot_properties[0] == {
        "source-silver-snapshot-id": str(silver_snapshot_id)
    }
    assert m.GOLD_SOURCE_SILVER_SNAPSHOT_KEY == "source-silver-snapshot-id"


def test_gold_without_provenance_is_rebuilt(monkeypatch) -> None:
    """GLD-01d: a Gold snapshot that says nothing certifies nothing.

    This is the post-maintenance shape: Trino ``optimize`` rewrites Gold's files
    and leaves a current snapshot carrying no ``source-silver-snapshot-id``.
    """

    catalog, persisted_silver, gold, metrics = setup_gold_run(
        monkeypatch, gold_source="persisted_silver", shadow=True
    )
    persisted_silver.df = table([row("a", 1)])
    persisted_silver.add_snapshot()
    gold.add_snapshot()

    m.run(catalog, metrics, "b2")

    assert gold.overwrite_calls == 1
    assert metrics.phase("gold")["gold_skipped"] is False


def test_provenance_is_read_from_the_current_snapshot_only(monkeypatch) -> None:
    """GLD-01e: an older matching snapshot must not vouch for a newer Gold state.

    Walking snapshot history would find the matching stamp and skip, certifying
    Gold against a Silver snapshot that no longer produced the current files.
    """

    catalog, persisted_silver, gold, metrics = setup_gold_run(
        monkeypatch, gold_source="persisted_silver", shadow=True
    )
    persisted_silver.df = table([row("a", 1)])
    persisted_silver.add_snapshot()
    silver_snapshot_id = persisted_silver.current_snapshot().snapshot_id
    gold.add_snapshot(**{"source-silver-snapshot-id": str(silver_snapshot_id)})
    gold.add_snapshot()

    m.run(catalog, metrics, "b2")

    assert gold.overwrite_calls == 1
    assert metrics.phase("gold")["gold_skipped"] is False


def test_a_silver_table_with_no_snapshots_is_never_certified(monkeypatch) -> None:
    """``None == None`` must not certify Gold against an empty lake."""

    catalog, persisted_silver, gold, metrics = setup_gold_run(
        monkeypatch, gold_source="persisted_silver", shadow=True
    )
    persisted_silver.df = table([row("a", 1)])
    assert m._snapshot_id(persisted_silver) is None

    m.run(catalog, metrics, "b2")
    second = FakeMetrics()
    m.run(catalog, second, "b2")

    assert gold.overwrite_calls == 2
    # Not merely "rebuilt": with no basis there is nothing truthful to stamp,
    # so a later cycle cannot be certified by this one either.
    assert gold.snapshot_properties == [{}, {}]


def test_unparsable_provenance_is_treated_as_absent(monkeypatch) -> None:
    """A snapshot property is a string written by whoever last committed."""

    catalog, persisted_silver, gold, metrics = setup_gold_run(
        monkeypatch, gold_source="persisted_silver", shadow=True
    )
    persisted_silver.df = table([row("a", 1)])
    persisted_silver.add_snapshot()
    gold.add_snapshot(**{"source-silver-snapshot-id": "snapshot-one"})

    m.run(catalog, metrics, "b2")

    assert gold.overwrite_calls == 1
    assert metrics.phase("gold")["gold_skipped"] is False


def test_legacy_gold_source_writes_every_cycle_and_stamps_nothing(monkeypatch) -> None:
    """The skip is scoped to Gold served from persisted Silver.

    Under ``GOLD_SOURCE=legacy`` the Gold input is the in-memory rebuild derived
    from Bronze, so a persisted-Silver stamp would not describe it - even though
    the Silver snapshot here does not move between the two cycles.
    """

    catalog, persisted_silver, gold, metrics = setup_gold_run(
        monkeypatch, gold_source="legacy", shadow=True
    )
    persisted_silver.df = table([row("a", 1)])
    persisted_silver.add_snapshot()

    m.run(catalog, metrics, "b2")
    second = FakeMetrics()
    m.run(catalog, second, "b2")

    assert gold.overwrite_calls == 2
    assert gold.snapshot_properties == [{}, {}]
    assert metrics.phase("gold")["gold_skipped"] is False
    assert second.phase("gold")["gold_skipped"] is False


# --- SHD-01: the durable shadow certificate and its identity -----------------
#
# The certificate is the only thing that can authorise skipping a correctness
# gate, so these specify the two directions separately: what it takes to be
# certified (all four identities, plus a passing result), and the far longer
# list of ways to end up not certified. Every entry in the second list must
# resolve to "run the comparison".

CERTIFIED_BRONZE = 101
CERTIFIED_SILVER = 202


def receipt(**overrides) -> dict:
    """A receipt certifying `CERTIFIED_BRONZE` / `CERTIFIED_SILVER` under today's contract."""

    stored = {
        "version": m.SHADOW_RECEIPT_VERSION,
        "bronze_snapshot_id": CERTIFIED_BRONZE,
        "silver_snapshot_id": CERTIFIED_SILVER,
        "runtime_identity": m._runtime_identity("b2"),
        "projection_identity": m._shadow_projection_identity(),
        "result": "equal",
        "compared_keys": 1,
        "certified_at": "2026-01-01T00:00:00+00:00",
        "cycle_id": "cycle-1",
    }
    stored.update(overrides)
    return stored


def certifies(stored: dict | None, **overrides) -> bool:
    """Ask the gate whether `stored` certifies the current state."""

    current = {
        "bronze_snapshot_id": CERTIFIED_BRONZE,
        "silver_snapshot_id": CERTIFIED_SILVER,
        "runtime_identity": m._runtime_identity("b2"),
        "projection_identity": m._shadow_projection_identity(),
    }
    current.update(overrides)
    return m.shadow_receipt_is_valid(stored, **current)


class ExplodingReadFS(FakeFS):
    def open_input_file(self, path: str):
        raise OSError("connection reset by peer")


class ExplodingWriteFS(FakeFS):
    def open_output_stream(self, path: str):
        raise OSError("no space left on device")


def test_projection_identity_changes_when_a_business_column_is_added(
    monkeypatch,
) -> None:
    """The most likely real contract change must invalidate every certificate."""

    before = m._shadow_projection_identity()
    monkeypatch.setattr(
        m, "SHADOW_BUSINESS_COLUMNS", m.SHADOW_BUSINESS_COLUMNS + ("discount",)
    )

    assert m._shadow_projection_identity() != before


def test_projection_identity_changes_when_a_column_is_reclassified(monkeypatch) -> None:
    """Moving a column from excluded to business changes what is compared."""

    before = m._shadow_projection_identity()
    monkeypatch.setattr(
        m, "SHADOW_BUSINESS_COLUMNS", m.SHADOW_BUSINESS_COLUMNS + ("kafka_offset",)
    )
    monkeypatch.setattr(m, "SHADOW_EXCLUDED_COLUMNS", ("kafka_timestamp",))

    assert m._shadow_projection_identity() != before


def test_projection_identity_changes_when_the_contract_version_is_bumped(
    monkeypatch,
) -> None:
    """The hand-bumped half covers semantics the column tuples cannot see."""

    before = m._shadow_projection_identity()
    monkeypatch.setattr(m, "SHADOW_CONTRACT_VERSION", m.SHADOW_CONTRACT_VERSION + 1)

    assert m._shadow_projection_identity() != before


def test_runtime_identity_separates_the_shadow_and_cutover_stages(monkeypatch) -> None:
    monkeypatch.setattr(m, "SHADOW_COMPARE_ENABLED", True)
    monkeypatch.setattr(m, "GOLD_SOURCE", "legacy")
    shadow_stage = m._runtime_identity("b2")
    monkeypatch.setattr(m, "GOLD_SOURCE", "persisted_silver")
    cutover_stage = m._runtime_identity("b2")

    assert shadow_stage != cutover_stage


def test_runtime_identity_separates_the_effective_silver_modes() -> None:
    assert m._runtime_identity("b2") != m._runtime_identity("legacy")


def test_no_receipt_never_certifies() -> None:
    assert certifies(None) is False


def test_a_matching_receipt_certifies() -> None:
    assert certifies(receipt()) is True


@pytest.mark.parametrize(
    "field",
    [
        "bronze_snapshot_id",
        "silver_snapshot_id",
        "runtime_identity",
        "projection_identity",
    ],
)
def test_a_receipt_differing_in_any_identity_never_certifies(field: str) -> None:
    assert certifies(receipt(**{field: "something-else"})) is False


def test_a_receipt_that_did_not_pass_never_certifies() -> None:
    assert certifies(receipt(result="mismatch")) is False


@pytest.mark.parametrize("unknown", ["bronze_snapshot_id", "silver_snapshot_id"])
def test_an_unknown_current_snapshot_id_never_certifies(unknown: str) -> None:
    """``None == None`` must never certify an empty lake."""

    assert certifies(receipt(**{unknown: None}), **{unknown: None}) is False


def test_a_receipt_round_trips_through_object_storage() -> None:
    filesystem = FakeFS({})
    m.save_shadow_receipt(filesystem, receipt())

    assert m.load_shadow_receipt(filesystem) == receipt()
    assert m._shadow_receipt_path() in filesystem.objects


def test_an_absent_receipt_reads_as_not_certified() -> None:
    assert m.load_shadow_receipt(FakeFS({})) is None


def test_malformed_receipt_json_reads_as_not_certified() -> None:
    filesystem = FakeFS({m._shadow_receipt_path(): b"{ not json"})

    assert m.load_shadow_receipt(filesystem) is None


def test_a_receipt_that_is_not_an_object_reads_as_not_certified() -> None:
    filesystem = FakeFS({m._shadow_receipt_path(): b"[1, 2, 3]"})

    assert m.load_shadow_receipt(filesystem) is None


def test_a_receipt_from_another_version_reads_as_not_certified() -> None:
    filesystem = FakeFS({})
    m.save_shadow_receipt(filesystem, receipt(version=m.SHADOW_RECEIPT_VERSION + 1))

    assert m.load_shadow_receipt(filesystem) is None


def test_an_unreadable_receipt_reads_as_not_certified() -> None:
    assert m.load_shadow_receipt(ExplodingReadFS({})) is None


def test_a_failed_receipt_write_never_breaks_the_cycle(capsys) -> None:
    """A lost certificate costs exactly one redundant comparison, nothing more."""

    m.save_shadow_receipt(ExplodingWriteFS({}), receipt())

    assert "shadow certification receipt" in capsys.readouterr().err.lower()


# --- SHD-01: the receipt-gated fast path -------------------------------------
#
# `setup_gold_run` leaves both doubles snapshotless, which is why every contract
# above still does the full work: an unknown snapshot id can never certify
# anything. These give Bronze and Silver a snapshot each, so a certificate can
# exist, and then specify what does and does not follow from one.


class RecordingFS(FakeFS):
    """A ``FakeFS`` that counts every object it was asked to read or write."""

    def __init__(self, objects: dict[str, bytes] | None = None) -> None:
        super().__init__(objects if objects is not None else {})
        self.reads = 0
        self.writes = 0

    def open_input_file(self, path: str):
        self.reads += 1
        return super().open_input_file(path)

    def open_output_stream(self, path: str):
        self.writes += 1
        return super().open_output_stream(path)


class Calls:
    """Count calls to named medallion functions without changing what they do.

    Same monkeypatch-capture idiom as `capture_gold_input` above: a skip is only
    observable as work that did not happen, so the specification has to count
    the calls rather than inspect the result.
    """

    def __init__(self, monkeypatch, *names: str) -> None:
        self.counts = dict.fromkeys(names, 0)
        for name in names:
            monkeypatch.setattr(m, name, self._counting(name, getattr(m, name)))

    def _counting(self, name: str, real):
        def wrapper(*args, **kwargs):
            self.counts[name] += 1
            return real(*args, **kwargs)

        return wrapper


def setup_certified_run(monkeypatch, *, gold_source: str = "persisted_silver"):
    """A shadow-validated run whose Bronze and Silver both carry a snapshot."""

    catalog, persisted_silver, gold, metrics = setup_gold_run(
        monkeypatch, gold_source=gold_source, shadow=True
    )
    persisted_silver.df = table([row("a", 1)])
    persisted_silver.add_snapshot()
    catalog.tables["bronze.orders"].add_snapshot()
    return catalog, persisted_silver, gold, metrics, RecordingFS()


def stored_receipt(filesystem: FakeFS) -> dict:
    return json.loads(filesystem.objects[m._shadow_receipt_path()])


def test_an_uncertified_cycle_compares_and_leaves_a_certificate(monkeypatch) -> None:
    catalog, persisted_silver, _gold, metrics, filesystem = setup_certified_run(
        monkeypatch
    )
    calls = Calls(monkeypatch, "compare_business_state")

    m.run(catalog, metrics, "b2", fs=filesystem)

    assert calls.counts["compare_business_state"] == 1
    receipt = stored_receipt(filesystem)
    silver_snapshot_id = persisted_silver.current_snapshot().snapshot_id
    assert receipt["result"] == "equal"
    assert receipt["version"] == m.SHADOW_RECEIPT_VERSION
    assert receipt["bronze_snapshot_id"] == 1
    assert receipt["silver_snapshot_id"] == silver_snapshot_id
    assert receipt["runtime_identity"] == m._runtime_identity("b2")
    assert receipt["projection_identity"] == m._shadow_projection_identity()
    assert receipt["compared_keys"] == 1
    assert receipt["cycle_id"] == metrics.cycle()["cycle_id"]
    assert receipt["certified_at"]


def test_a_certified_cutover_cycle_does_no_validation_work(monkeypatch) -> None:
    """SHD-01: unmoved state under a matching contract costs nothing to revalidate."""

    catalog, persisted_silver, _gold, metrics, filesystem = setup_certified_run(
        monkeypatch, gold_source="persisted_silver"
    )
    m.run(catalog, metrics, "b2", fs=filesystem)

    calls = Calls(
        monkeypatch, "_pin_bronze_boundary", "build_silver", "compare_business_state"
    )
    gold_inputs = []
    real_build_gold = m.build_gold

    def capture_gold_input(df):
        gold_inputs.append(df)
        return real_build_gold(df)

    monkeypatch.setattr(m, "build_gold", capture_gold_input)
    second = FakeMetrics()
    m.run(catalog, second, "b2", fs=filesystem)

    assert calls.counts == {
        "_pin_bronze_boundary": 0,
        "build_silver": 0,
        "compare_business_state": 0,
    }
    assert second.cycle()["status"] == "success"
    # The cycle still completes, and Gold is still served from persisted Silver.
    assert gold_inputs and gold_inputs[0] is persisted_silver.df


def test_a_certified_shadow_cycle_still_builds_the_projection_gold_needs(
    monkeypatch,
) -> None:
    """Under GOLD_SOURCE=legacy the rebuild is Gold's input, not validation work."""

    catalog, _persisted_silver, gold, metrics, filesystem = setup_certified_run(
        monkeypatch, gold_source="legacy"
    )
    m.run(catalog, metrics, "b2", fs=filesystem)

    calls = Calls(
        monkeypatch, "_pin_bronze_boundary", "build_silver", "compare_business_state"
    )
    second = FakeMetrics()
    m.run(catalog, second, "b2", fs=filesystem)

    assert calls.counts["_pin_bronze_boundary"] == 1
    assert calls.counts["build_silver"] == 1
    assert calls.counts["compare_business_state"] == 0
    assert gold.overwrite_calls == 2


def test_a_moved_bronze_snapshot_forces_revalidation(monkeypatch) -> None:
    catalog, _persisted_silver, _gold, metrics, filesystem = setup_certified_run(
        monkeypatch
    )
    m.run(catalog, metrics, "b2", fs=filesystem)

    catalog.tables["bronze.orders"].add_snapshot()
    calls = Calls(monkeypatch, "compare_business_state")
    second = FakeMetrics()
    m.run(catalog, second, "b2", fs=filesystem)

    assert calls.counts["compare_business_state"] == 1
    assert second.cycle()["shadow_comparisons"] == 1


def test_a_silver_snapshot_that_moved_independently_forces_revalidation(
    monkeypatch,
) -> None:
    """The B2 recovery case: Silver can move without Bronze moving."""

    catalog, persisted_silver, _gold, metrics, filesystem = setup_certified_run(
        monkeypatch
    )
    m.run(catalog, metrics, "b2", fs=filesystem)

    persisted_silver.add_snapshot()
    calls = Calls(monkeypatch, "compare_business_state")
    second = FakeMetrics()
    m.run(catalog, second, "b2", fs=filesystem)

    assert calls.counts["compare_business_state"] == 1
    assert second.cycle()["shadow_comparisons"] == 1


@pytest.mark.parametrize("identity", ["runtime_identity", "projection_identity"])
def test_a_changed_identity_forces_revalidation(monkeypatch, identity: str) -> None:
    catalog, _persisted_silver, _gold, metrics, filesystem = setup_certified_run(
        monkeypatch
    )
    m.run(catalog, metrics, "b2", fs=filesystem)

    receipt = stored_receipt(filesystem)
    receipt[identity] = "from-another-contract"
    filesystem.objects[m._shadow_receipt_path()] = json.dumps(receipt).encode("utf-8")
    calls = Calls(monkeypatch, "compare_business_state")
    second = FakeMetrics()
    m.run(catalog, second, "b2", fs=filesystem)

    assert calls.counts["compare_business_state"] == 1


def test_a_shadow_mismatch_still_fails_closed_and_certifies_nothing(
    monkeypatch,
) -> None:
    catalog, persisted_silver, gold, metrics, filesystem = setup_certified_run(
        monkeypatch
    )
    persisted_silver.df = table([row("a", 9, amount=99)])

    with pytest.raises(ValueError, match="Shadow comparison failed"):
        m.run(catalog, metrics, "b2", fs=filesystem)

    assert gold.overwrite_calls == 0
    assert filesystem.objects == {}
    assert filesystem.writes == 0


def test_unknown_snapshot_ids_never_touch_the_filesystem(monkeypatch) -> None:
    """No id, no certificate, no object-store call, and the full work runs."""

    catalog, persisted_silver, _gold, metrics = setup_gold_run(
        monkeypatch, gold_source="persisted_silver", shadow=True
    )
    persisted_silver.df = table([row("a", 1)])

    def refuse(*args, **kwargs):
        raise AssertionError("a filesystem was constructed for an uncertifiable cycle")

    monkeypatch.setattr(m, "get_fs", refuse)
    filesystem = RecordingFS()
    calls = Calls(monkeypatch, "compare_business_state")

    m.run(catalog, metrics, "b2", fs=filesystem)

    assert m._bronze_snapshot_id(catalog) is None
    assert filesystem.reads == 0
    assert filesystem.writes == 0
    assert calls.counts["compare_business_state"] == 1


def test_shadow_skipped_is_the_inverse_of_a_comparison_that_ran(
    monkeypatch, capsys
) -> None:
    catalog, _persisted_silver, _gold, metrics, filesystem = setup_certified_run(
        monkeypatch
    )
    m.run(catalog, metrics, "b2", fs=filesystem)
    second = FakeMetrics()
    m.run(catalog, second, "b2", fs=filesystem)

    assert metrics.phase("shadow")["shadow_comparisons"] == 1
    assert metrics.phase("shadow")["shadow_skipped"] is False
    assert metrics.cycle()["shadow_comparisons"] == 1
    assert metrics.cycle()["shadow_skipped"] is False

    assert second.phase("shadow")["shadow_comparisons"] == 0
    assert second.phase("shadow")["shadow_skipped"] is True
    assert second.cycle()["shadow_comparisons"] == 0
    assert second.cycle()["shadow_skipped"] is True

    markers = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith(m.CYCLE_COMPLETE_MARKER)
    ]
    assert "shadow=compared" in markers[0]
    assert "shadow=skipped" in markers[-1]


def test_an_absent_bronze_table_has_no_snapshot_id() -> None:
    """`_bronze_snapshot_id` reads metadata only and never raises for an absent table."""

    assert m._bronze_snapshot_id(SharedFakeCatalog({})) is None
