# Warehouse dbt documents

The `dbt/warehouse` project (`warehouse_transform`, PostgreSQL) is documented in
four numbered documents. Each answers a different question.

| Document | Question it answers |
|---|---|
| [W1 — dbt ownership](W1-dbt-ownership.md) | Who owns which relation, and what does each test layer prove? |
| [W2 — execution contract](W2-execution-contract.md) | What does Airflow guarantee at run time, and how does a replay behave? |
| [W3 — mutation gate](W3-mutation-gate.md) | Would the test suite notice if the SQL became subtly wrong? |
| [W4 — architecture gate](W4-dbt-architecture-gate.md) | Does the dependency graph obey the layer rule? |

To run the checks these documents describe, see
[TESTING.md](../TESTING.md#warehouse-dbt). For the place of the warehouse in the
wider platform, see [ARCHITECTURE.md](../ARCHITECTURE.md).
