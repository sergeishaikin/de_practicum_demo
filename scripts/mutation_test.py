"""SQL mutation testing harness for the Tier-1 warehouse models.

Ordinary tests answer "does the current SQL behave correctly?". This answers the
stronger question: "would the suite notice if the SQL became subtly wrong?" It
applies a catalogue of known-dangerous semantic mutations to an isolated copy of
the dbt project and requires the intended test to fail for each one.

Production SQL is never modified: every mutation is applied to a throwaway copy
under a temporary directory, which is removed even if a dbt run crashes.

Adding a mutation
-----------------
Append a `Mutation` to CATALOGUE with:
  * `name`        - stable identifier, used in the report
  * `path`        - project-relative file to mutate
  * `find`/`into` - an exact, unique string replacement (asserted to apply)
  * `killer`      - the dbt selector for the smallest test expected to fail
  * `rationale`   - the regression class this guards against

Prefer the narrowest selector that should fail: the harness runs that first and
never runs the full suite, which keeps the gate fast.

Usage
-----
    python scripts/mutation_test.py [--json report.json] [--self-test]

Exit codes: 0 all required mutations killed; 1 at least one survived or errored.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "dbt" / "warehouse"

KILLED = "killed"
SURVIVED = "survived"
INVALID = "invalid"
EQUIVALENT = "equivalent"
ERROR = "error"


@dataclass(frozen=True)
class Mutation:
    name: str
    path: str
    find: str
    into: str
    killer: str
    rationale: str
    expect: str = KILLED


CATALOGUE: list[Mutation] = [
    Mutation(
        name="left_join_to_inner_join",
        path="models/marts/v_order_items_wide.sql",
        find="left join {{ ref('stg_core__orders') }} o",
        into="inner join {{ ref('stg_core__orders') }} o",
        killer="order_items_wide_keeps_items_without_a_matching_order",
        rationale="an inner join silently drops items whose header is missing",
    ),
    Mutation(
        name="full_join_to_left_join",
        path="models/marts/v_reconcile_sales_daily.sql",
        find="full join source_sales s",
        into="left join source_sales s",
        killer="reconcile_sales_daily_reports_both_sides_of_the_full_join",
        rationale="a left join hides source-only days, so unreconciled data reads as reconciled",
    ),
    Mutation(
        name="drop_ingest_date_predicate",
        path="models/marts/v_reconcile_sales_daily.sql",
        find="\n   and oi.ingest_date = o.ingest_date",
        into="",
        killer="reconcile_sales_daily_ignores_cross_batch_ingest_dates",
        rationale="items from one batch would reconcile against headers from another",
    ),
    Mutation(
        name="count_distinct_to_count",
        path="models/marts/v_sales_daily.sql",
        find="count(distinct order_id) as orders_cnt",
        into="count(order_id) as orders_cnt",
        killer="sales_daily_counts_orders_distinctly_and_sums_money_per_day",
        rationale="orders_cnt would count line items, inflating every daily order count",
    ),
    Mutation(
        name="reverse_reconciliation_arithmetic",
        path="models/marts/v_reconcile_sales_daily.sql",
        find="(coalesce(m.gross_sales, 0) - coalesce(s.source_gross_sales, 0))",
        into="(coalesce(s.source_gross_sales, 0) - coalesce(m.gross_sales, 0))",
        killer="reconcile_sales_daily_reports_both_sides_of_the_full_join",
        rationale="diff_amount would report the wrong sign, inverting every verdict",
    ),
    Mutation(
        name="drop_coalesce_on_mart_side",
        path="models/marts/v_reconcile_sales_daily.sql",
        find="coalesce(m.gross_sales, 0)::numeric(12, 2) as mart_gross_sales",
        into="m.gross_sales::numeric(12, 2) as mart_gross_sales",
        killer="reconcile_sales_daily_reports_both_sides_of_the_full_join",
        rationale="a source-only day would report NULL instead of 0",
    ),
    Mutation(
        name="sum_wrong_money_column",
        path="models/marts/v_sales_daily.sql",
        find="sum(price)::numeric(12, 2) as gross_sales",
        into="sum(freight_value)::numeric(12, 2) as gross_sales",
        killer="sales_daily_counts_orders_distinctly_and_sums_money_per_day",
        rationale="gross sales would report freight, a plausible but wrong figure",
    ),
    Mutation(
        name="state_count_distinct_to_count",
        path="models/marts/v_customer_state_daily.sql",
        find="count(distinct order_id) as orders_cnt",
        into="count(order_id) as orders_cnt",
        killer="customer_state_daily_partitions_each_day_by_state",
        rationale="per-state order counts would double-count multi-item orders",
    ),
]

# Exercises the harness itself: a real semantic change that the current suite does
# NOT cover, so it must be reported as survived. Kept out of CATALOGUE so the gate
# does not fail on a known, documented gap.
SELF_TEST = Mutation(
    name="selftest_order_status_from_header",
    path="models/marts/v_order_items_wide.sql",
    find="  oi.order_status,",
    into="  o.order_status,",
    killer="order_items_wide_keeps_items_without_a_matching_order",
    rationale=(
        "taking order_status from the header instead of the item is a real change, "
        "but no unit test asserts that column, so it survives - which is exactly "
        "what the harness must report"
    ),
    expect=SURVIVED,
)


@dataclass
class Result:
    mutation: Mutation
    status: str
    killed_by: list[str] = field(default_factory=list)
    detail: str = ""


def _dbt_executable() -> str:
    override = os.environ.get("DBT_EXECUTABLE")
    if override:
        return override
    for candidate in (
        ROOT / ".venv-dbt-warehouse" / "Scripts" / "dbt.exe",
        ROOT / ".venv-dbt-warehouse" / "bin" / "dbt",
    ):
        if candidate.is_file():
            return str(candidate)
    return "dbt"


def _apply(mutation: Mutation, project: Path) -> None:
    target = project / mutation.path
    source = target.read_text(encoding="utf-8")
    if mutation.find not in source:
        raise LookupError(
            f"{mutation.name}: pattern not found in {mutation.path}. "
            "The model changed - update the mutation or retire it."
        )
    if source.count(mutation.find) != 1:
        raise LookupError(f"{mutation.name}: pattern is not unique in {mutation.path}.")
    target.write_text(source.replace(mutation.find, mutation.into), encoding="utf-8")


def _run(mutation: Mutation, project: Path) -> Result:
    proc = subprocess.run(
        [
            _dbt_executable(),
            "test",
            "--project-dir",
            str(project),
            "--profiles-dir",
            str(project),
            "--select",
            mutation.killer,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = proc.stdout + proc.stderr

    # A mutation that stops the project compiling exercises nothing, so it must
    # not be reported as coverage.
    if "Compilation Error" in output or "Parsing Error" in output:
        return Result(mutation, INVALID, detail="mutated SQL no longer compiles")
    if "Database Error" in output and "FAIL" not in output:
        return Result(
            mutation, INVALID, detail="mutated SQL is not valid for the warehouse"
        )
    if "Nothing to do" in output or "NO-OP=1" in output:
        return Result(
            mutation, ERROR, detail=f"selector matched no test: {mutation.killer}"
        )

    killers = sorted(
        {
            match.group(1).split("::")[-1]
            for match in re.finditer(r"FAIL\s+\d*\s*([\w.]+::[\w.]+|[\w.]+)", output)
            if "::" in match.group(1)
        }
    )
    if proc.returncode != 0 and killers:
        return Result(mutation, KILLED, killed_by=killers)
    if proc.returncode == 0:
        return Result(mutation, SURVIVED, detail="every selected test still passed")
    return Result(mutation, ERROR, detail=output.strip().splitlines()[-1][:200])


def evaluate(mutation: Mutation) -> Result:
    """Copy the project, mutate the copy, run the killer test, always clean up."""
    tmp = Path(tempfile.mkdtemp(prefix=f"mut-{mutation.name}-"))
    try:
        project = tmp / "warehouse"
        shutil.copytree(
            PROJECT,
            project,
            ignore=shutil.ignore_patterns("target", "dbt_packages", "logs"),
        )
        _apply(mutation, project)
        return _run(mutation, project)
    except LookupError as exc:
        return Result(mutation, ERROR, detail=str(exc))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="write a machine-readable report")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="also run the mutation that is expected to survive",
    )
    args = parser.parse_args()

    mutations = list(CATALOGUE) + ([SELF_TEST] if args.self_test else [])
    results = [evaluate(mutation) for mutation in mutations]

    width = max(len(result.mutation.name) for result in results)
    print(f"{'mutation'.ljust(width)}  {'status'.ljust(10)}  killed by")
    print("-" * (width + 14 + 40))
    for result in results:
        killed_by = ", ".join(result.killed_by) or result.detail
        print(
            f"{result.mutation.name.ljust(width)}  "
            f"{result.status.ljust(10)}  {killed_by}"
        )

    counts = {
        status: sum(1 for result in results if result.status == status)
        for status in (KILLED, SURVIVED, INVALID, EQUIVALENT, ERROR)
    }
    print()
    print(f"Mutations: {len(results)}")
    for status in (KILLED, SURVIVED, INVALID, EQUIVALENT, ERROR):
        print(f"{(status.capitalize() + ':').ljust(11)}{counts[status]}")

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "counts": counts,
                    "results": [
                        {
                            "mutation": result.mutation.name,
                            "path": result.mutation.path,
                            "status": result.status,
                            "expected": result.mutation.expect,
                            "killed_by": result.killed_by,
                            "detail": result.detail,
                            "rationale": result.mutation.rationale,
                        }
                        for result in results
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    unexpected = [r for r in results if r.status != r.mutation.expect]
    if unexpected:
        print()
        for result in unexpected:
            print(
                f"UNEXPECTED: {result.mutation.name} expected {result.mutation.expect}, "
                f"got {result.status} - {result.detail}"
            )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
