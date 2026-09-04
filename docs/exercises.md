# Hands-on tasks

Базовое демо уже показывает готовый pipeline. Эти задания нужны, чтобы сделать что-то руками.

## Как проходить

Есть три нормальных маршрута. Не надо считать провалом, если ты прошел только первый или первые два.

**Маршрут 1. Запустить pipeline и посмотреть слои**

Подними стенд, запусти DAG, посмотри, как данные прошли путь `CSV -> stg -> core -> marts`, и прогони базовые проверки.

**Маршрут 2. SQL-задача**

Добавь новую витрину поверх `core.orders`. Это маршрут для тех, кто уже умеет SQL и хочет понять, как разовый запрос превращается в проверяемую витрину.

> Это учебное упражнение на чистом SQL. Production-витрины в `dbt/warehouse`
> живут по другому правилу: mart-модель не вызывает `source()`, а читает dbt
> staging-модель через `ref()`. См.
> [W4 — dbt architecture gate](warehouse/W4-dbt-architecture-gate.md).

**Маршрут 3. Airflow-задача**

Добавь quality gate в DAG. Это уже не просто SQL: здесь появляется оркестрация, task chain и остановка pipeline при плохом качестве данных.

Сначала пройди основной сценарий:

```powershell
docker compose up -d
scripts\show_layers.cmd
```

Запусти вручную DAG `warehouse_orders_ingestion` в Airflow и убедись, что после его успеха `warehouse_marts_validation` запустился автоматически через Asset:

```powershell
scripts\run_checks.cmd
```

macOS/Linux:

```bash
bash scripts/run_checks.sh
```

## Как откатиться, если сломал файл

Если работаешь в git-репозитории:

```powershell
git restore db/tasks/01_create_payment_type_daily.sql
git restore dags/warehouse_orders.py
```

Если git-команды пока не знакомы, проще скачать репозиторий заново в отдельную папку. Не надо руками чинить десятки строк, если цель была пройти первое demo.

Если менял SQL-объекты в `db/init`, пересоздай demo-volume:

```powershell
docker compose down -v
docker compose up -d
```

## Task 1. SQL: новая витрина по оплатам

Уровень: SQL.

Airflow трогать не нужно.

Нужно создать витрину:

```text
marts.v_payment_type_daily
```

Файл для работы:

```text
db/tasks/01_create_payment_type_daily.sql
```

Витрина должна иметь колонки:

```text
sales_date
main_payment_type
orders_cnt
payment_sum
avg_payment
```

Источник:

```text
core.orders
```

Логика:

- `sales_date`: дата заказа
- `main_payment_type`: основной тип оплаты
- `orders_cnt`: количество заказов
- `payment_sum`: сумма оплат
- `avg_payment`: средняя сумма оплаты

Проверка:

```powershell
scripts\check_task_sql.cmd
```

macOS/Linux:

```bash
bash scripts/check_task_sql.sh
```

Что проверяется:

- view существует
- строки есть
- `sales_date` не null
- `main_payment_type` не null
- сумма `payment_sum` совпадает с `core.orders.payment_value`

<details>
<summary>Подсказка 1</summary>

Начни с таблицы `core.orders`. В ней уже есть дата заказа, тип оплаты и сумма оплаты.

</details>

<details>
<summary>Подсказка 2</summary>

Тебе нужна группировка:

```sql
group by order_purchase_date, main_payment_type
```

</details>

<details>
<summary>Подсказка 3</summary>

Для среднего платежа можно использовать:

```sql
avg(payment_value)::numeric(12, 2)
```

</details>

<details>
<summary>Подсказка 4</summary>

Каркас запроса:

```sql
create or replace view marts.v_payment_type_daily as
select
  order_purchase_date as sales_date,
  main_payment_type,
  count(*)::int as orders_cnt,
  sum(payment_value)::numeric(12, 2) as payment_sum,
  avg(payment_value)::numeric(12, 2) as avg_payment
from core.orders
group by order_purchase_date, main_payment_type;
```

</details>

**Важно**: Решение должно лежать в db/tasks/01_create_payment_type_daily.sql.

## Task 2. Airflow: quality gate по оплатам

Уровень: простой Airflow + Python.

> **Внимание: в текущем репозитории это задание уже решено.** Task
> `quality.check_payment_reconcile` включён в downstream DAG в `dags/warehouse_orders.py`,
> поэтому `scripts\check_task_airflow.cmd` проходит сразу. Чтобы выполнить
> задание самостоятельно, временно соедини `validate_marts` напрямую с `publish_mart_assets`, минуя payment task —
> получится описанное ниже исходное состояние. Готовую реализацию можно
> использовать как эталон для сверки.

Нужно добавить в DAG новую задачу:

```text
check_payment_reconcile
```

Файл для работы:

```text
dags/warehouse_orders.py
```

Сейчас цепочка задач такая:

```text
validate_marts -> publish_mart_assets -> write_audit
```

Должно стать так:

```text
validate_marts -> check_payment_reconcile -> publish_mart_assets -> write_audit
```

Что должна делать новая задача:

1. Посчитать сумму `payment_value` в `stg.order_payments`.
2. Посчитать сумму `payment_value` в `core.orders`.
3. Если разница больше `0.01`, упасть с `AirflowException`.

Контрольные точки:

- DAG открывается в Airflow без import error.
- В списке tasks появился `check_payment_reconcile`.
- Новый task стоит между `validate_marts` и `publish_mart_assets`.
- Если суммы совпадают, feature test проходит.
- Если quality gate падает, ошибка должна быть понятной: stg sum, core sum, diff.

В файле DAG есть TODO-комментарии рядом с `write_audit`. Это не готовое решение, а рельсы, чтобы не искать точку входа вслепую.

Проверка:

```powershell
scripts\check_task_airflow.cmd
```

macOS/Linux:

```bash
bash scripts/check_task_airflow.sh
```

Что проверяется:

- Airflow видит task `check_payment_reconcile`
- feature test проходит успешно
- quality gate не ломает основной pipeline

<details>
<summary>Подсказка 1</summary>

В DAG уже есть функция `_connect()`. Используй её, не создавай подключение заново.

</details>

<details>
<summary>Подсказка 2</summary>

Новая задача может быть похожа на `write_audit`, но без insert. Нужен только `select`, сравнение и `AirflowException`.

</details>

<details>
<summary>Подсказка 3</summary>

SQL для проверки:

```sql
select
  (select coalesce(sum(payment_value), 0) from stg.order_payments) as stg_payment_sum,
  (select coalesce(sum(payment_value), 0) from core.orders) as core_payment_sum;
```

</details>

<details>
<summary>Подсказка 4</summary>

В Python сравнение может выглядеть так:

```python
diff = abs(stg_payment_sum - core_payment_sum)
if diff > 0.01:
    raise AirflowException(
        f"Payment reconcile failed: stg={stg_payment_sum}, core={core_payment_sum}, diff={diff}"
    )
```

</details>

<details>
<summary>Подсказка 5</summary>

Не забудь изменить цепочку задач в конце DAG:

```python
mart_state >> check_payment_reconcile() >> publish_mart_assets(mart_state)
```

</details>

## Что дальше

Если оба задания прошли, ты сделал две реальные DE-операции:

- добавил новую витрину поверх `core`
- добавил quality gate в Airflow DAG

Это маленький объём кода, но паттерн настоящий.
