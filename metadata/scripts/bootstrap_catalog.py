"""Create the repository-controlled OpenMetadata service graph.

The script is intentionally idempotent and emits no credentials.  It runs in
the pinned OpenMetadata ingestion image, so the generated service definitions
use the same SDK version as the server rather than relying on a host package.
"""

from __future__ import annotations

import base64
import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from metadata.generated.schema.api.domains.createDomain import CreateDomainRequest
from metadata.generated.schema.api.services.createDatabaseService import (
    CreateDatabaseServiceRequest,
)
from metadata.generated.schema.api.services.createMessagingService import (
    CreateMessagingServiceRequest,
)
from metadata.generated.schema.api.services.createPipelineService import (
    CreatePipelineServiceRequest,
)
from metadata.generated.schema.api.teams.createTeam import CreateTeamRequest
from metadata.generated.schema.entity.domains.domain import DomainType
from metadata.generated.schema.entity.services.connections.database.common.basicAuth import (
    BasicAuth as DatabaseBasicAuth,
)
from metadata.generated.schema.entity.services.connections.database.postgresConnection import (
    PostgresConnection,
)
from metadata.generated.schema.entity.services.connections.database.trinoConnection import (
    TrinoConnection,
)
from metadata.generated.schema.entity.services.connections.messaging.kafkaConnection import (
    KafkaConnection,
)
from metadata.generated.schema.entity.services.messagingService import (
    MessagingConnection,
    MessagingServiceType,
)
from metadata.generated.schema.entity.services.connections.pipeline.airflowConnection import (
    AirflowConnection,
)
from metadata.generated.schema.entity.services.connections.pipeline.openLineageConnection import (
    ConsumerOffsets,
    KafkaBrokerConfig,
    OpenLineageConnection,
    SecurityProtocol,
)
from metadata.generated.schema.entity.services.pipelineService import (
    PipelineConnection,
    PipelineServiceType,
)
from metadata.generated.schema.entity.services.databaseService import (
    DatabaseConnection,
    DatabaseServiceType,
)
from metadata.generated.schema.entity.utils.airflowRestApiConnection import (
    AirflowRestApiConnection,
)
from metadata.generated.schema.entity.utils.common.basicAuthConfig import (
    BasicAuth as AirflowBasicAuth,
)
from metadata.generated.schema.entity.teams.team import TeamType
from metadata.sdk import configure
from metadata.sdk.entities import DatabaseServices, Domains, Pipelines, Teams


API = os.getenv("METADATA_API", "http://metadata-server:8585/api").rstrip("/")


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def login() -> str:
    email = os.getenv("METADATA_ADMIN_EMAIL", "admin@open-metadata.org")
    password = required("METADATA_ADMIN_PASSWORD")
    encoded = base64.b64encode(password.encode("utf-8")).decode("ascii")
    request = Request(
        f"{API}/v1/users/login",
        data=json.dumps({"email": email, "password": encoded}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=15) as response:
        payload = json.load(response)
    token = payload.get("accessToken") or payload.get("token")
    if not token:
        raise RuntimeError("OpenMetadata login returned no token")
    return token


def existing_or_create(collection, name: str, request):
    try:
        entity = collection.retrieve_by_name(name)
        return entity if entity is not None else collection.create(request)
    except Exception:
        return collection.create(request)


def ensure_raw_service(token: str, path: str, name: str, request) -> None:
    """Create a service kind not exposed by this SDK's entity facade."""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    lookup = Request(f"{API}{path}/name/{name}", headers=headers, method="GET")
    try:
        with urlopen(lookup, timeout=15):
            return
    except HTTPError as error:
        if error.code != 404:
            raise
    payload = request.model_dump(by_alias=True, exclude_none=True, mode="json")
    create = Request(
        f"{API}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(create, timeout=15):
        return


def main() -> None:
    token = login()
    configure(host=API, jwt_token=token)

    orders_domain = existing_or_create(
        Domains,
        "orders",
        CreateDomainRequest(
            domainType=DomainType.Source_aligned,
            name="orders",
            displayName="Orders",
            description="Deterministic orders domain for the DE Practicum demo.",
        ),
    )
    platform_domain = existing_or_create(
        Domains,
        "platform",
        CreateDomainRequest(
            domainType=DomainType.Source_aligned,
            name="platform",
            displayName="Platform",
            description="Platform-owned orchestration and runtime assets.",
        ),
    )
    existing_or_create(
        Teams,
        "data-platform",
        CreateTeamRequest(
            teamType=TeamType.Group,
            name="data-platform",
            displayName="Data Platform",
            description="Owner of warehouse and catalog assets.",
        ),
    )
    existing_or_create(
        Teams,
        "streaming-platform",
        CreateTeamRequest(
            teamType=TeamType.Group,
            name="streaming-platform",
            displayName="Streaming Platform",
            description="Owner of Kafka and Iceberg runtime assets.",
        ),
    )

    reader = required("METADATA_SOURCE_READER_USER")
    reader_password = required("METADATA_SOURCE_READER_PASSWORD")
    dbt_database = required("POSTGRES_DB")
    lineage_topic = required("METADATA_LINEAGE_TOPIC")

    ensure_raw_service(
        token,
        "/v1/services/messagingServices",
        "demo_kafka",
        CreateMessagingServiceRequest(
            name="demo_kafka",
            displayName="Demo Kafka",
            description="Read-only metadata view of demo Kafka topics.",
            serviceType=MessagingServiceType.Kafka,
            domains=[orders_domain.fullyQualifiedName.root],
            connection=MessagingConnection(
                config=KafkaConnection(
                    bootstrapServers="kafka:9092",
                    topicFilterPattern={
                        "includes": ["^(orders|" + lineage_topic + ")$"]
                    },
                    supportsMetadataExtraction=True,
                )
            ),
        ),
    )

    existing_or_create(
        DatabaseServices,
        "warehouse_postgres",
        CreateDatabaseServiceRequest(
            name="warehouse_postgres",
            displayName="Warehouse PostgreSQL",
            description="Read-only warehouse metadata source; dbt remains execution authority.",
            serviceType=DatabaseServiceType.Postgres,
            domains=[orders_domain.fullyQualifiedName.root],
            connection=DatabaseConnection(
                config=PostgresConnection(
                    username=reader,
                    authType=DatabaseBasicAuth(password=reader_password),
                    hostPort="de-demo-postgres:5432",
                    database=dbt_database,
                    ingestAllDatabases=False,
                    supportsDBTExtraction=True,
                )
            ),
        ),
    )
    existing_or_create(
        DatabaseServices,
        "lakehouse_trino",
        CreateDatabaseServiceRequest(
            name="lakehouse_trino",
            displayName="Lakehouse Trino",
            description="Read-only Trino authority for Iceberg physical entities.",
            serviceType=DatabaseServiceType.Trino,
            domains=[orders_domain.fullyQualifiedName.root],
            connection=DatabaseConnection(
                config=TrinoConnection(
                    username=reader,
                    hostPort="de-demo-trino:8080",
                    catalog="iceberg",
                )
            ),
        ),
    )
    airflow_user = os.getenv("METADATA_AIRFLOW_USER", "metadata_reader")
    airflow_password = required("METADATA_AIRFLOW_PASSWORD")
    existing_or_create(
        Pipelines,
        "demo_airflow",
        CreatePipelineServiceRequest(
            name="demo_airflow",
            displayName="Demo Airflow",
            description="Existing repository Airflow; OpenMetadata is a read-only consumer.",
            serviceType=PipelineServiceType.Airflow,
            domains=[platform_domain.fullyQualifiedName.root],
            connection=PipelineConnection(
                config=AirflowConnection(
                    hostPort="http://de-demo-airflow:8080",
                    connection=AirflowRestApiConnection(
                        authConfig=AirflowBasicAuth(
                            username=airflow_user,
                            password=airflow_password,
                        )
                    ),
                )
            ),
        ),
    )
    existing_or_create(
        Pipelines,
        "runtime_openlineage",
        CreatePipelineServiceRequest(
            name="runtime_openlineage",
            displayName="Runtime OpenLineage",
            description="Dedicated Kafka consumer for NG-0.2 runtime events.",
            serviceType=PipelineServiceType.OpenLineage,
            domains=[platform_domain.fullyQualifiedName.root],
            connection=PipelineConnection(
                config=OpenLineageConnection(
                    brokerConfig=KafkaBrokerConfig(
                        brokersUrl="kafka:9092",
                        topicName=lineage_topic,
                        consumerGroupName=os.getenv(
                            "METADATA_LINEAGE_CONSUMER_GROUP",
                            "openmetadata-runtime-lineage",
                        ),
                        consumerOffsets=ConsumerOffsets.earliest,
                        securityProtocol=SecurityProtocol.PLAINTEXT,
                    ),
                    namespaceToServiceMapping={
                        "iceberg://iceberg-rest": "lakehouse_trino",
                        "kafka://kafka": "demo_kafka",
                    },
                )
            ),
        ),
    )

    # Keep stdout machine-readable but credential-free for acceptance receipts.
    print(
        json.dumps(
            {
                "api": API,
                "services": [
                    "warehouse_postgres",
                    "lakehouse_trino",
                    "demo_kafka",
                    "demo_airflow",
                    "runtime_openlineage",
                ],
                "domains": ["orders", "platform"],
                "teams": ["data-platform", "streaming-platform"],
            }
        )
    )


if __name__ == "__main__":
    main()
