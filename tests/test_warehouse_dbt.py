"""Repository contracts for the Phase 03B warehouse dbt project."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "dbt" / "warehouse"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_warehouse_dbt_runtime_is_pinned_and_separate() -> None:
    assert (PROJECT / "dbt_project.yml").exists()
    assert (PROJECT / "profiles.yml.example").exists()
    requirements = (
        (PROJECT / "requirements.in").read_text(encoding="utf-8").splitlines()
    )
    assert requirements == ["dbt-core==1.12.2", "dbt-postgres==1.11.0"]
    locked = (PROJECT / "requirements.txt").read_text(encoding="utf-8")
    assert "dbt-core==1.12.2" in locked
    assert "dbt-postgres==1.11.0" in locked


def test_sources_keep_airflow_owned_boundaries_explicit() -> None:
    sources = (PROJECT / "models" / "sources.yml").read_text(encoding="utf-8")
    for source_name in ("staging", "core"):
        assert f"name: {source_name}" in sources
    for table_name in ("orders", "order_items", "order_payments", "customers"):
        assert f"name: {table_name}" in sources
    assert "owner:airflow" in sources


def test_marts_preserve_existing_relation_names_and_sql_boundaries() -> None:
    expected = {
        "v_order_items_wide": "v_order_items_wide",
        "v_sales_daily": "v_sales_daily",
        "v_customer_state_daily": "v_customer_state_daily",
        "v_reconcile_sales_daily": "v_reconcile_sales_daily",
    }
    for model, alias in expected.items():
        sql = (PROJECT / "models" / "marts" / f"{model}.sql").read_text(
            encoding="utf-8"
        )
        assert f"alias='{alias}'" in sql
        assert "{{ config(" in sql
    assert "source('core', 'order_items')" in (
        PROJECT / "models" / "marts" / "v_sales_daily.sql"
    ).read_text(encoding="utf-8")
    reconcile = (
        PROJECT / "models" / "marts" / "v_reconcile_sales_daily.sql"
    ).read_text(encoding="utf-8")
    assert "source('staging', 'orders')" in reconcile
    assert "ref('v_sales_daily')" in reconcile


def test_quality_contracts_and_selectors_are_present() -> None:
    schema = (PROJECT / "models" / "marts" / "schema.yml").read_text(encoding="utf-8")
    for contract_model in (
        "v_order_items_wide",
        "v_sales_daily",
        "v_customer_state_daily",
        "v_reconcile_sales_daily",
    ):
        assert f"name: {contract_model}" in schema
    assert schema.count("enforced: true") == 4
    for test_name in (
        "mart_reconciliation.sql",
        "order_items_wide_grain.sql",
        "payment_reconciliation.sql",
    ):
        assert (PROJECT / "tests" / test_name).exists()
    selectors = (PROJECT / "selectors.yml").read_text(encoding="utf-8")
    assert "warehouse_contracts" in selectors
    assert "warehouse_reconciliation" in selectors


def test_core_rebuild_transaction_remains_airflow_owned() -> None:
    source = read("dags/warehouse_orders.py")
    assert '_execute_sql_file(conn, SQL_DIR / "10_rebuild_core.sql")' in source
    assert "warehouse_orders_ingestion()" in source
    assert not source.rstrip().endswith("warehouse_marts_validation()")


def test_cosmos_warehouse_dag_uses_watcher_and_explicit_publication() -> None:
    source = read("dags/warehouse_dbt.py")
    assert "ExecutionMode.WATCHER" in source
    assert 'dbt_id="warehouse_marts_validation"' not in source
    assert 'dag_id="warehouse_marts_validation"' in source
    assert "render_config=RenderConfig(emit_datasets=False)" in source
    assert "publish_mart_assets" in source
    assert "PIPELINE_AUDIT_ASSET" in source
    assert "get_current_context" in source
