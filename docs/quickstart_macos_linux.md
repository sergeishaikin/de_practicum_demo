# Quickstart for macOS and Linux

Полный путь от чистой машины до отчета.

## 1. Поставь инструменты

Обязательно:

- Docker Desktop или Docker Engine с Docker Compose v2
- Git
- uv 0.12.5

Удобно, но не обязательно:

- VS Code или PyCharm
- DBeaver для просмотра Postgres

На macOS проще всего поставить Docker Desktop. На Linux проверь, что команда `docker compose version` работает без старого `docker-compose`.

## 2. Проверь Docker

Запусти Docker Desktop или Docker Engine.

```bash
docker --version
docker compose version
docker info
```

Если `docker info` падает, сначала почини Docker. Дальше demo не запустится.

## 3. Скачай репозиторий

```bash
git clone https://github.com/dim4eg91/de_practicum_demo.git de_practicum_demo
cd de_practicum_demo
```

Проверь, что ты в корне проекта:

```bash
ls docker-compose.yml
```

Файл `.env` создавать не обязательно. Настройки по умолчанию уже есть в `docker-compose.yml`. Пример лежит в `.env.example`.

## 4. Запусти doctor

```bash
bash scripts/doctor.sh
```

Doctor проверит Docker, Compose, CSV-файлы, порты `15432` и `18085`.

## 5. Подними demo-стенд

```bash
docker compose up -d
```

Проверь контейнеры:

```bash
docker compose ps
```

Ожидаемо:

- `de-demo-postgres` healthy
- `de-demo-airflow` running

## 6. Посмотри состояние до DAG

```bash
bash scripts/show_layers.sh
```

До запуска DAG в БД должны быть пустые слои: `stg`, `core`, `marts`.

## 7. Запусти DAG

Открой Airflow:

```text
http://localhost:18085
```

Логин: `admin`

Пароль: `admin`

В Airflow:

1. Найди `demo_core_marts_pipeline`.
2. Включи DAG.
3. Нажми Trigger DAG.
4. Дождись `success`.

## 8. Проверь результат

```bash
bash scripts/run_checks.sh
```

Ожидаемо:

- строки появились в `stg`, `core`, `marts`
- duplicate grain rows = 0
- null keys = 0
- reconcile diff = 0.00
- smoke status = success

## 9. Собери отчет

```bash
bash scripts/build_report.sh
```

Открой:

```text
reports/demo_quality_report.html
```

На macOS:

```bash
open reports/demo_quality_report.html
```

На Linux:

```bash
xdg-open reports/demo_quality_report.html
```

## 10. Сделай задания руками

Открой:

```text
docs/exercises.md
```

Там два задания:

- SQL-витрина по оплатам
- Airflow quality gate

Проверки:

```bash
bash scripts/check_task_sql.sh
bash scripts/check_task_airflow.sh
```

## 11. Останови стенд

```bash
docker compose down
```

Удалить все demo-данные:

```bash
docker compose down -v
```
