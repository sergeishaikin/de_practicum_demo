# Quickstart for Windows

Полный путь от пустой машины до отчета.

## 1. Поставь инструменты

Обязательно:

- Docker Desktop for Windows
- Git
- uv 0.12.5

Удобно, но не обязательно:

- VS Code или PyCharm
- DBeaver для просмотра Postgres

Если Docker Desktop попросит войти в аккаунт, войди или зарегистрируйся. Публиковать образы никуда не нужно.

## 2. Проверь Docker

Открой Docker Desktop и дождись рабочего состояния engine.

В PowerShell:

```powershell
docker --version
docker compose version
```

Если Docker пишет про WSL, открой PowerShell от имени администратора:

```powershell
wsl --update
```

После этого перезапусти Docker Desktop.

## 3. Скачай репозиторий

```powershell
cd D:\
git clone https://github.com/dim4eg91/de_practicum_demo.git de_practicum_demo
cd D:\de_practicum_demo
```

Проверь, что ты в корне проекта:

```powershell
dir docker-compose.yml
```

Если файла нет, ты не там. Дальше команды запускать бессмысленно.

Файл `.env` создавать не обязательно. Настройки по умолчанию уже есть в `docker-compose.yml`. Пример лежит в `.env.example`.

## 4. Запусти doctor

```powershell
scripts\doctor.cmd
```

Doctor проверит Docker, Compose, CSV-файлы, порты `15432` и `18085`.

## 5. Подними demo-стенд

```powershell
docker compose up -d
```

Если Docker Hub падает с `EOF`, а у тебя уже собран основной учебный стенд:

```powershell
docker compose -f docker-compose.local-airflow.yml up -d
```

Это запасной локальный вариант. Для обычного публичного запуска используй `docker compose up -d`.

Проверь контейнеры:

```powershell
docker compose ps
```

Ожидаемо:

- `de-demo-postgres` healthy
- `de-demo-airflow` running

## 6. Посмотри состояние до DAG

```powershell
scripts\show_layers.cmd
```

До запуска DAG в БД должны быть пустые слои: `stg`, `core`, `marts`.

## 7. Запусти DAG

Открой Airflow:

```text
http://localhost:18085
```

Логин: `admin`

Пароль: `admin`

Если Airflow показывает желтые предупреждения про SQLite metadata DB и SequentialExecutor, это нормально для demo. Здесь Airflow упрощен ради первого локального запуска.

В Airflow:

1. Найди `demo_core_marts_pipeline`.
2. Включи DAG.
3. Нажми Trigger DAG.
4. Дождись `success`.

## 8. Проверь результат

```powershell
scripts\run_checks.cmd
```

Ожидаемо:

- строки появились в `stg`, `core`, `marts`
- duplicate grain rows = 0
- null keys = 0
- reconcile diff = 0.00
- smoke status = success

## 9. Собери отчет

```powershell
scripts\build_report.cmd
```

Открой:

```text
reports\demo_quality_report.html
```

Схема demo-пайплайна:

```text
docs\schema.md
```

Короткая DBML-схема для dbdiagram.io:

```text
docs\dbdiagram_overview.dbml
```

Полная DBML-схема:

```text
docs\dbdiagram_demo.dbml
```

## 10. Сделай задания руками

Открой:

```text
docs\exercises.md
```

Там два задания:

- SQL-витрина по оплатам
- Airflow quality gate

Проверки:

```powershell
scripts\check_task_sql.cmd
scripts\check_task_airflow.cmd
```

## 11. Останови стенд

```powershell
docker compose down
```

Удалить все demo-данные:

```powershell
docker compose down -v
```
