# Data Engineering Practicum Demo

Локальный demo-стенд курса без Spark, MinIO и Jupyter. Внутри только Postgres, Airflow, 4 CSV-файла и короткий pipeline: `data/raw` -> `stg` -> `core` -> `marts`.

Полный путь для Windows лежит в [docs/quickstart_windows.md](docs/quickstart_windows.md).

## Пререквизиты

Минимум:

- Docker Desktop
- Git

Удобно дополнительно:

- VS Code или PyCharm
- DBeaver для просмотра Postgres

Справка по Docker Desktop: [docs/docker_desktop_windows.md](docs/docker_desktop_windows.md).

Настройки по умолчанию уже зашиты в `docker-compose.yml`. Если хочешь переопределить пользователя, пароль или timezone, скопируй `.env.example` в `.env` и измени значения.

## Что внутри

Схема demo-проекта специально короткая:

```text
CSV files -> stg tables -> core tables -> marts views -> checks -> HTML report
```


## Что есть до DAG

После `docker compose up -d` в Postgres уже есть схемы и объекты:

- `stg`: пустые приемные таблицы для CSV
- `core`: пустые очищенные таблицы
- `marts`: пустые витрины и smoke-таблица запусков



CSV лежат в `data/raw`. В БД данных еще нет, пока не запущен DAG.

Проверить пустое состояние:

```powershell
scripts\show_layers.cmd
```

Ожидаемо увидишь `rows_count = 0` и `no data` по слоям.

![show_layers.png](imgs/show_layers.png)

## Запуск

Обычный вариант:

```powershell
docker compose up -d
```

![docker_compose_up.png](imgs/docker_compose_up.png)

Если Docker Hub отдает `EOF` при скачивании `apache/airflow`, но на машине уже есть совместимый локальный образ Airflow:

```powershell
docker compose -f docker-compose.local-airflow.yml up -d
```

Это запасной локальный вариант. Для обычного запуска основной командой остается `docker compose up -d`.

Airflow: http://localhost:18085

Логин: `admin`

Пароль: `admin`

Желтые предупреждения Airflow про SQLite metadata DB и SequentialExecutor нормальны для этого demo. Это не production-настройка, а упрощение, чтобы стенд запускался локально в 2 контейнерах.

Postgres для DBeaver или psql:

- host: `localhost`
- port: `15432`
- database: `dwh`
- user: `app`
- password: `app`

![pg_connection.png](imgs/pg_connection.png)

## Сценарий

1. Открой Airflow.
2. Найди DAG `demo_core_marts_pipeline`.
3. Включи DAG переключателем.
4. Нажми Trigger DAG.
5. После успешного run выполни проверки.

![demo_core_marts_pipeline.png](imgs/demo_core_marts_pipeline.png)

Проверки после DAG:

```powershell
scripts\run_checks.cmd
```

![show_layers_after.png](imgs/show_layers_after.png)

Если нужен именно PowerShell-скрипт:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_checks.ps1
```

## Что должно получиться

После DAG данные появятся в слоях:

- `stg.orders`, `stg.order_items`, `stg.order_payments`, `stg.customers`
- `core.orders`, `core.order_items`
- `marts.v_sales_daily`, `marts.v_customer_state_daily`, `marts.v_order_items_wide`

![demo_core_marts_pipeline_after.png](imgs/demo_core_marts_pipeline_after.png)

Smoke-проверка должна показать `status = success`, `duplicate_grain_rows = 0`, `null_key_rows = 0`, `max_reconcile_diff = 0.00`.

## Отчет

После успешного DAG можно собрать HTML-отчет:

```powershell
scripts\build_report.cmd
```

Открой файл:

```text
reports\demo_quality_report.html
```

Отчет показывает слои загрузки, quality scorecard, grain/null-key проверки, reconcile и smoke последнего запуска.

## Задания руками

После базового демо можно сделать два маленьких задания:

- SQL: добавить витрину `marts.v_payment_type_daily`
- Airflow: добавить quality gate `check_payment_reconcile`

Инструкция: [docs/exercises.md](docs/exercises.md).

Проверки:

```powershell
scripts\check_task_sql.cmd
scripts\check_task_airflow.cmd
```

## Справка

- [docs/quickstart_windows.md](docs/quickstart_windows.md)
- [docs/schema.md](docs/schema.md)
- [docs/exercises.md](docs/exercises.md)
- [docs/docker_desktop_windows.md](docs/docker_desktop_windows.md)
- [docs/troubleshooting.md](docs/troubleshooting.md)

## Остановка

```powershell
docker compose down
```

Полная очистка данных:

```powershell
docker compose down -v
```
