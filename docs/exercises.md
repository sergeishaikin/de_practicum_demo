# Hands-on tasks

Базовое демо уже показывает готовый pipeline. Эти задания нужны, чтобы сделать что-то руками.

## Как проходить

Есть три нормальных маршрута. Не надо считать провалом, если ты прошел только первый или первые два.

**Маршрут 1. Запустить pipeline и посмотреть слои**

Подними стенд, запусти DAG, посмотри, как данные прошли путь `CSV -> stg -> core -> marts`, и прогони базовые проверки.

**Маршрут 2. SQL-задача**

Добавь новую витрину поверх `core.orders`. Это маршрут для тех, кто уже умеет SQL и хочет понять, как разовый запрос превращается в проверяемую витрину.

**Маршрут 3. Airflow-задача**

Добавь quality gate в DAG. Это уже не просто SQL: здесь появляется оркестрация, task chain и остановка pipeline при плохом качестве данных.

Сначала пройди основной сценарий:

```powershell
docker compose up -d
scripts\show_layers.cmd
```

Запусти DAG `demo_core_marts_pipeline` в Airflow и убедись, что проверки проходят:

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
git restore dags/demo_core_marts_pipeline.py
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
> `check_payment_reconcile` включён в цепочку `dags/demo_core_marts_pipeline.py`,
> поэтому `scripts\check_task_airflow.cmd` проходит сразу. Чтобы выполнить
> задание самостоятельно, сначала убери задачу из вызова `chain(...)` —
> получится описанное ниже исходное состояние. Готовую реализацию можно
> использовать как эталон для сверки.

Нужно добавить в DAG новую задачу:

```text
check_payment_reconcile
```

Файл для работы:

```text
dags/demo_core_marts_pipeline.py
```

Сейчас цепочка задач такая:

```text
load_raw_csv_to_stg -> rebuild_core_and_marts -> write_audit
```

Должно стать так:

```text
load_raw_csv_to_stg -> rebuild_core_and_marts -> check_payment_reconcile -> write_audit
```

Что должна делать новая задача:

1. Посчитать сумму `payment_value` в `stg.order_payments`.
2. Посчитать сумму `payment_value` в `core.orders`.
3. Если разница больше `0.01`, упасть с `AirflowException`.

Контрольные точки:

- DAG открывается в Airflow без import error.
- В списке tasks появился `check_payment_reconcile`.
- Новый task стоит между `rebuild_core_and_marts` и `write_audit`.
- Если суммы совпадают, DAG test проходит.
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
- DAG test проходит успешно
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
load_raw_csv_to_stg() >> rebuild_core_and_marts() >> check_payment_reconcile() >> write_audit("{{ run_id }}")
```

</details>

## Что дальше

Если оба задания прошли, ты сделал две реальные DE-операции:

- добавил новую витрину поверх `core`
- добавил quality gate в Airflow DAG

Это маленький объём кода, но паттерн настоящий.
