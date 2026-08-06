# Local Data Engineering Platform

A Docker Compose-based local data platform for batch processing, streaming, orchestration, object storage, analytics, and interactive development.

## Architecture

```text
                                  ┌─────────────────┐
                                  │     Airflow     │
                                  │ localhost:18085 │
                                  └────────┬────────┘
                                           │
                                           ▼
┌──────────────────┐   Spark Connect   ┌───────────────────┐
│     Jupyter      │ ─────────────────▶│  Spark Connect    │
│ localhost:18888  │   sc://...:15002  │ localhost:15002   │
└────────┬─────────┘                   └─────────┬─────────┘
         │ Classic Spark                          │
         ▼                                        ▼
┌──────────────────┐                   ┌───────────────────┐
│   Spark Master   │──────────────────▶│   Spark Worker    │
│ localhost:18080  │                   │ localhost:18081   │
└────────┬─────────┘                   └───────────────────┘
         │
         ├──────────────────────────────┐
         │                              │
         ▼                              ▼
┌──────────────────┐          ┌──────────────────┐
│    PostgreSQL    │          │      MinIO       │
│ localhost:15432  │          │ API: 19000       │
└────────┬─────────┘          │ Console: 19001   │
         │                    └──────────────────┘
         ▼
┌──────────────────┐
│     Metabase     │
│ localhost:13000  │
└──────────────────┘

┌──────────────────┐          ┌──────────────────┐
│      Kafka       │─────────▶│     Kafka UI     │
│ localhost:19092  │          │ localhost:18090  │
└────────┬─────────┘          └──────────────────┘
         │
         ▼
Spark Structured Streaming
```

## Components and URLs

| Component | Purpose | Host access |
|---|---|---|
| Airflow | Pipeline orchestration | `http://localhost:18085` |
| Spark Master UI | Cluster and application management | `http://localhost:18080` |
| Spark Worker UI | Worker status and resources | `http://localhost:18081` |
| Spark Connect | Remote Spark endpoint | `sc://localhost:15002` |
| Spark Connect UI | Connect driver UI | `http://localhost:14040` |
| JupyterLab | Interactive PySpark development | `http://localhost:18888` |
| PostgreSQL | Data warehouse | `localhost:15432` |
| MinIO API | S3-compatible endpoint | `http://localhost:19000` |
| MinIO Console | Object storage UI | `http://localhost:19001` |
| Kafka | Event-streaming broker | `localhost:19092` |
| Kafka UI | Kafka administration | `http://localhost:18090` |
| Metabase | Analytics and dashboards | `http://localhost:13000` |

## Requirements

- Windows 10 or Windows 11
- Docker Desktop using Linux containers
- WSL2 backend
- PowerShell 5.1 or PowerShell 7
- At least 12 GB RAM available to Docker; 16 GB is preferable

## Initial setup

Create the runtime environment file:

```powershell
Copy-Item .env.example .env
```

Validate Compose:

```powershell
docker compose `
  --env-file .\.env `
  -f .\docker-compose.yml `
  -f .\docker-compose.extended.yml `
  config
```

Build and start:

```powershell
.\stack.ps1 build
.\stack.ps1 up
.\stack.ps1 status
```

## Commands

```powershell
.\stack.ps1 up
.\stack.ps1 down
.\stack.ps1 build
.\stack.ps1 build -NoCache
.\stack.ps1 build -Service jupyter
.\stack.ps1 status
.\stack.ps1 logs
.\stack.ps1 logs -Service kafka
.\stack.ps1 logs -Service spark-worker -Tail 500
.\stack.ps1 logs -Service spark-worker -NoFollow
```

## Jupyter authentication

```powershell
docker exec de-demo-jupyter jupyter server list
```

Replace container port `8888` with host port `18888` in the returned URL.

## PostgreSQL

Host connection:

```text
Host: localhost
Port: 15432
Database: dwh
Username: value from POSTGRES_USER
Password: value from POSTGRES_PASSWORD
```

Container connection:

```text
de-demo-postgres:5432
```

## MinIO

Console: `http://localhost:19001`

Internal S3 endpoint: `http://minio:9000`

## Kafka

Kafka UI: `http://localhost:18090`

Internal bootstrap server: `kafka:9092`

Create the `orders` topic:

```powershell
docker exec de-demo-kafka `
  /opt/kafka/bin/kafka-topics.sh `
  --bootstrap-server kafka:9092 `
  --create `
  --if-not-exists `
  --topic orders `
  --partitions 3 `
  --replication-factor 1
```

## Spark modes

Classic mode:

```python
from pyspark.sql import SparkSession

spark = (
    SparkSession.builder
    .appName("classic-session")
    .master("spark://spark-master:7077")
    .config("spark.pyspark.python", "/usr/bin/python3")
    .getOrCreate()
)
```

Spark Connect:

```python
from pyspark.sql import SparkSession

spark = (
    SparkSession.builder
    .remote("sc://spark-connect:15002")
    .appName("connect-session")
    .getOrCreate()
)
```

Classic Spark and Spark Connect can compete for the same local worker. Stop unused applications when resources are exhausted.

## Health checks

```powershell
docker ps --format "table {{.Names}}\t{{.Status}}"
docker inspect de-demo-kafka --format "{{json .State.Health}}"
docker inspect de-demo-spark-connect --format "{{json .State.Health}}"
```

## Safe stop versus destructive reset

Safe stop keeps persistent volumes:

```powershell
.\stack.ps1 down
```

> **Warning:** reset removes named Docker volumes and may delete PostgreSQL data, MinIO objects, Metabase configuration, and other persisted local state.

Interactive reset:

```powershell
.\stack.ps1 reset
```

Type `RESET` when prompted.

Non-interactive reset:

```powershell
.\stack.ps1 reset -Force
```

## Troubleshooting

No Spark resources: open `http://localhost:18080` and stop old applications.

Jupyter token rejected:

```powershell
docker exec de-demo-jupyter jupyter server list
```

Kafka logs:

```powershell
.\stack.ps1 logs -Service kafka
```

Validate after Compose edits:

```powershell
docker compose `
  --env-file .\.env `
  -f .\docker-compose.yml `
  -f .\docker-compose.extended.yml `
  config --services
```
