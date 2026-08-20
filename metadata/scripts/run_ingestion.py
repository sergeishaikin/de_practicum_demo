"""Run repository-controlled OpenMetadata connector workflows.

Workflow YAML is rendered into a temporary directory so JWTs never become
repository files or persistent container state.  The only durable inputs are
the service names, source identities, and dbt artifact paths declared here.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

import yaml


API = os.getenv("METADATA_API", "http://metadata-server:8585/api").rstrip("/")


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def token() -> str:
    password = required("METADATA_ADMIN_PASSWORD")
    body = {
        "email": os.getenv("METADATA_ADMIN_EMAIL", "admin@open-metadata.org"),
        "password": base64.b64encode(password.encode()).decode(),
    }
    request = Request(
        f"{API}/v1/users/login",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=15) as response:
        payload = json.load(response)
    return payload.get("accessToken") or payload["token"]


def server_config(jwt: str) -> dict:
    return {
        "hostPort": API,
        "authProvider": "openmetadata",
        "securityConfig": {"jwtToken": jwt},
    }


def workflow(source: dict, jwt: str) -> dict:
    return {
        "source": source,
        "sink": {"type": "metadata-rest", "config": {}},
        "workflowConfig": {
            "loggerLevel": os.getenv("METADATA_LOG_LEVEL", "INFO"),
            "openMetadataServerConfig": server_config(jwt),
        },
    }


def postgres_connection() -> dict:
    return {
        "type": "Postgres",
        "username": required("METADATA_SOURCE_READER_USER"),
        "authType": {"password": required("METADATA_SOURCE_READER_PASSWORD")},
        "hostPort": "de-demo-postgres:5432",
        "database": required("POSTGRES_DB"),
        "ingestAllDatabases": False,
        "schemaFilterPattern": {"excludes": ["^information_schema$"]},
        "databaseFilterPattern": {"excludes": ["^template1$", "^template0$"]},
        "sslMode": "disable",
    }


def trino_connection() -> dict:
    return {
        "type": "Trino",
        "username": required("METADATA_SOURCE_READER_USER"),
        "hostPort": "de-demo-trino:8080",
        "catalog": "iceberg",
    }


def airflow_connection() -> dict:
    return {
        "type": "Airflow",
        "hostPort": "http://de-demo-airflow:8080",
        "connection": {
            "type": "RestAPI",
            "authConfig": {
                "username": os.getenv("METADATA_AIRFLOW_USER", "metadata_reader"),
                "password": required("METADATA_AIRFLOW_PASSWORD"),
            },
            "apiVersion": "auto",
            "verifySSL": False,
        },
    }


def kafka_connection() -> dict:
    return {
        "type": "Kafka",
        "bootstrapServers": "kafka:9092",
        "securityProtocol": "PLAINTEXT",
        "topicFilterPattern": {
            "includes": [
                "^(orders|%s)$" % required("METADATA_LINEAGE_TOPIC"),
            ]
        },
    }


def openlineage_connection() -> dict:
    return {
        "type": "OpenLineage",
        "brokerConfig": {
            "brokersUrl": "kafka:9092",
            "topicName": required("METADATA_LINEAGE_TOPIC"),
            "consumerGroupName": os.getenv(
                "METADATA_LINEAGE_CONSUMER_GROUP", "openmetadata-runtime-lineage"
            ),
            "consumerOffsets": "earliest",
            "poolTimeout": 3.0,
            "sessionTimeout": 60,
            "securityProtocol": "PLAINTEXT",
        },
        "namespaceToServiceMapping": {
            "iceberg://iceberg-rest": "lakehouse_trino",
            "kafka://kafka": "demo_kafka",
        },
    }


def sources() -> dict[str, dict]:
    return {
        "postgres": {
            "type": "postgres",
            "serviceName": "warehouse_postgres",
            "serviceConnection": {"config": postgres_connection()},
            "sourceConfig": {
                "config": {
                    "type": "DatabaseMetadata",
                    "includeTables": True,
                    "includeViews": True,
                    "markDeletedTables": False,
                }
            },
        },
        "trino": {
            "type": "trino",
            "serviceName": "lakehouse_trino",
            "serviceConnection": {"config": trino_connection()},
            "sourceConfig": {
                "config": {
                    "type": "DatabaseMetadata",
                    "includeTables": True,
                    "includeViews": True,
                }
            },
        },
        "airflow": {
            "type": "airflow",
            "serviceName": "demo_airflow",
            "serviceConnection": {"config": airflow_connection()},
            "sourceConfig": {
                "config": {
                    "type": "PipelineMetadata",
                }
            },
        },
        "kafka": {
            "type": "kafka",
            "serviceName": "demo_kafka",
            "serviceConnection": {"config": kafka_connection()},
            "sourceConfig": {
                "config": {
                    "type": "MessagingMetadata",
                    "generateSampleData": False,
                }
            },
        },
        "openlineage": {
            "type": "openlineage",
            "serviceName": "runtime_openlineage",
            "serviceConnection": {"config": openlineage_connection()},
            # OpenLineage is a pipeline source in the ingestion workflow
            # schema; its broker is selected by the service connection above.
            "sourceConfig": {
                "config": {
                    "type": "PipelineMetadata",
                    "lineageInformation": {"dbServiceNames": ["lakehouse_trino"]},
                    "includeLineage": True,
                }
            },
        },
        "dbt_warehouse": {
            "type": "dbt",
            "serviceName": "warehouse_postgres",
            "serviceConnection": {"config": postgres_connection()},
            "sourceConfig": {
                "config": {
                    "type": "DBT",
                    "dbtConfigSource": {
                        "dbtConfigType": "local",
                        "dbtCatalogFilePath": "/opt/metadata-artifacts/warehouse/catalog.json",
                        "dbtManifestFilePath": "/opt/metadata-artifacts/warehouse/manifest.json",
                        "dbtRunResultsFilePath": "/opt/metadata-artifacts/warehouse/run_results.json",
                    },
                    "dbtUpdateDescriptions": True,
                    "includeTags": True,
                }
            },
        },
        "dbt_semantic": {
            "type": "dbt",
            "serviceName": "lakehouse_trino",
            "serviceConnection": {"config": trino_connection()},
            "sourceConfig": {
                "config": {
                    "type": "DBT",
                    "dbtConfigSource": {
                        "dbtConfigType": "local",
                        "dbtCatalogFilePath": "/opt/metadata-artifacts/semantic/catalog.json",
                        "dbtManifestFilePath": "/opt/metadata-artifacts/semantic/manifest.json",
                        "dbtRunResultsFilePath": "/opt/metadata-artifacts/semantic/run_results.json",
                    },
                    "dbtUpdateDescriptions": True,
                    "includeTags": True,
                }
            },
        },
    }


def run(kind: str) -> None:
    jwt = token()
    selected = sources()
    if kind == "static":
        names = [
            "postgres",
            "trino",
            "airflow",
            "kafka",
            "dbt_warehouse",
            "dbt_semantic",
        ]
    elif kind == "runtime":
        names = ["openlineage"]
    else:
        names = list(selected)

    with tempfile.TemporaryDirectory(prefix="openmetadata-workflow-") as directory:
        for name in names:
            path = Path(directory) / f"{name}.yaml"
            path.write_text(
                yaml.safe_dump(workflow(selected[name], jwt), sort_keys=False),
                encoding="utf-8",
            )
            subprocess.run(["metadata", "ingest", "-c", str(path)], check=True)

    # The official OpenLineage workflow remains primary.  This bounded,
    # idempotent supplement only materializes the proven object-store input
    # representation that OpenMetadata 1.13.3 cannot resolve natively.
    if kind in ("runtime", "all"):
        from openlineage_container_adapter import run as run_object_store_adapter

        run_object_store_adapter(jwt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("static", "runtime", "all"))
    run(parser.parse_args().kind)
