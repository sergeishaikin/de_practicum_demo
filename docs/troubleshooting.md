# Troubleshooting

Короткая диагностика demo-стенда.

## Быстрая проверка через doctor

Windows:

```powershell
scripts\doctor.cmd
```

macOS/Linux:

```bash
bash scripts/doctor.sh
```

Doctor проверяет корень проекта, Docker, Docker Compose, CSV-файлы, порты `15432` и `18085`, и показывает текущие Compose-контейнеры.

## Ты в корне проекта?

```powershell
dir docker-compose.yml
```

Если файла нет, перейди в папку репозитория.

## Контейнеры поднялись?

```powershell
docker compose ps
```

Ожидаемо:

- `de-demo-postgres` healthy
- `de-demo-airflow` running

Логи:

```powershell
docker compose logs --tail=100 de-demo-postgres
docker compose logs --tail=100 de-demo-airflow
```

## Postgres отвечает?

```powershell
docker compose exec -T de-demo-postgres psql -U app -d dwh -c "select 1 as ok;"
```

DBeaver:

- Host: `localhost`
- Port: `15432`
- Database: `dwh`
- User: `app`
- Password: `app`

## Airflow не открывается

Проверь:

```powershell
docker compose ps
docker compose logs --tail=100 de-demo-airflow
```

URL:

```text
http://localhost:18085
```

Логин не требуется. Compose привязывает Airflow к `127.0.0.1`, а локальный
Simple Auth Manager разрешает этому loopback-only UI работать в all-admin mode.

## Airflow не подключается к metadata DB

Airflow 3.3.1 использует отдельную базу `airflow_meta` в PostgreSQL.
Проверьте, что в `.env` заданы `AIRFLOW_DB_USER`, `AIRFLOW_DB_NAME` и отдельный
URL-safe `AIRFLOW_DB_PASSWORD`, затем посмотрите результат one-shot сервиса:

```powershell
docker logs de-demo-airflow-db-init
```

Сервис идемпотентен и должен завершиться с кодом `0` до запуска Airflow.

## PowerShell блокирует `.ps1`

Используй `.cmd`:

```powershell
scripts\run_checks.cmd
scripts\build_report.cmd
```

Или так:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_checks.ps1
```

## Проверка задания падает

Для стартового репозитория это нормально.

`scripts\check_task_sql.cmd` должен падать, пока ты не переписал `db/tasks/01_create_payment_type_daily.sql`.

`scripts\check_task_airflow.cmd` в текущем репозитории **проходит**: task `check_payment_reconcile` уже включён в цепочку `dags/demo_core_marts_pipeline.py`. Чтобы выполнить Задание 2 самостоятельно, сначала убери его из вызова `chain(...)` — тогда проверка снова начнёт падать.

Если базовые проверки проходят, а task-check падает, значит проблема именно в задании:

```powershell
scripts\run_checks.cmd
scripts\check_task_sql.cmd
scripts\check_task_airflow.cmd
```

Откатить стартовые файлы:

```powershell
git restore db/tasks/01_create_payment_type_daily.sql
git restore dags/demo_core_marts_pipeline.py
```

## Нужно применить init SQL заново

Postgres init-скрипты выполняются только при создании пустого volume. Если менял `db/init`, нужен сброс demo-данных:

```powershell
docker compose down -v
docker compose up -d
```

Это удалит только локальные данные demo-стенда.

## Что прислать для диагностики

Одним сообщением:

Windows:

```powershell
scripts\doctor.cmd
docker compose ps
docker compose logs --tail=100 de-demo-postgres
docker compose logs --tail=100 de-demo-airflow
scripts\show_layers.cmd
scripts\run_checks.cmd
```

macOS/Linux:

```bash
bash scripts/doctor.sh
docker compose ps
docker compose logs --tail=100 de-demo-postgres
docker compose logs --tail=100 de-demo-airflow
bash scripts/show_layers.sh
bash scripts/run_checks.sh
```
