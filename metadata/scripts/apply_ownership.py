"""Apply deterministic owner/domain metadata from repository JSON config."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from metadata.sdk import configure
from metadata.sdk.entities import Domains, Pipelines, Tables, Teams
from metadata.generated.schema.type.entityReference import EntityReference
from metadata.generated.schema.type.entityReferenceList import EntityReferenceList


API = os.getenv("METADATA_API", "http://metadata-server:8585/api").rstrip("/")
ROOT = Path("/opt/metadata")


def login() -> str:
    password = os.environ["METADATA_ADMIN_PASSWORD"]
    payload = {
        "email": os.getenv("METADATA_ADMIN_EMAIL", "admin@open-metadata.org"),
        "password": base64.b64encode(password.encode()).decode(),
    }
    request = Request(
        f"{API}/v1/users/login",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=15) as response:
        body = json.load(response)
    return body.get("accessToken") or body["token"]


def retrieve(collection, fqn: str):
    return collection.retrieve_by_name(fqn, fields=["owners", "domains", "tags"])


def apply_entity(
    collection, fqn: str, team_ref: EntityReference, domains: list[EntityReference]
) -> None:
    entity = retrieve(collection, fqn)
    entity.owners = EntityReferenceList([team_ref])
    entity.domains = EntityReferenceList(domains)
    collection.update(entity)


def apply_topic(
    fqn: str,
    team_ref: EntityReference,
    domains: list[EntityReference],
) -> None:
    """Topics are not exposed by the 1.13 SDK entity facade; use its API."""
    path = f"{API}/v1/topics/name/{quote(fqn, safe='')}?fields=owners,domains"
    auth_headers = {"Authorization": f"Bearer {TOKEN}"}
    with urlopen(Request(path, headers=auth_headers), timeout=15) as response:
        entity = json.load(response)
    owner = team_ref if isinstance(team_ref, dict) else team_ref.model_dump(mode="json")
    domain_refs = [
        domain if isinstance(domain, dict) else domain.model_dump(mode="json")
        for domain in domains
    ]
    payload = [
        {"op": "replace", "path": "/owners", "value": [owner]},
        {"op": "replace", "path": "/domains", "value": domain_refs},
    ]
    update_path = f"{API}/v1/topics/{entity['id']}"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json-patch+json",
    }
    request = Request(
        update_path,
        data=json.dumps(payload).encode(),
        headers=headers,
        method="PATCH",
    )
    with urlopen(request, timeout=15):
        pass


def main() -> None:
    global TOKEN
    TOKEN = login()
    configure(host=API, jwt_token=TOKEN)
    mapping = json.loads(
        (ROOT / "config" / "ownership.json").read_text(encoding="utf-8")
    )
    topic_suffix = os.environ["METADATA_LINEAGE_TOPIC"]
    missing: list[str] = []

    for team_name, assignments in mapping["teams"].items():
        team = Teams.retrieve_by_name(team_name)
        team_ref = Teams.to_entity_reference(team)
        domains = [
            Domains.to_entity_reference(Domains.retrieve_by_name(domain))
            for domain in assignments.get("domains", [])
        ]
        for fqn in assignments.get("tables", []):
            try:
                apply_entity(Tables, fqn, team_ref, domains)
            except Exception as error:
                missing.append(f"{fqn}: {type(error).__name__}: {error}")
        for fqn in assignments.get("pipelines", []):
            try:
                apply_entity(Pipelines, fqn, team_ref, domains)
            except Exception as error:
                missing.append(f"{fqn}: {type(error).__name__}: {error}")
        for fqn in assignments.get("topics", []):
            try:
                apply_topic(
                    fqn.replace("${METADATA_LINEAGE_TOPIC}", topic_suffix),
                    team_ref,
                    domains,
                )
            except Exception as error:
                missing.append(f"{fqn}: {type(error).__name__}: {error}")

    if missing:
        raise SystemExit("missing catalog entities: " + ", ".join(sorted(missing)))
    print(json.dumps({"ownership": "applied", "teams": sorted(mapping["teams"])}))


if __name__ == "__main__":
    main()
