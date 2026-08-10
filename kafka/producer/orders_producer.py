from __future__ import annotations

import json
import hashlib
import os
import random
import signal
import sys
import time
import uuid
from datetime import datetime, timezone

from confluent_kafka import Producer


BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
TOPIC = os.getenv("KAFKA_TOPIC", "orders")
EVENTS_PER_SECOND = float(os.getenv("EVENTS_PER_SECOND", "2"))
# ``SOURCE_EPOCH_ID`` is deliberately producer-supplied.  The default keeps
# the historical demo producer usable while a new-baseline deployment pins an
# immutable, explicitly named epoch through its environment.
SOURCE_EPOCH_ID = os.getenv("SOURCE_EPOCH_ID", "legacy").strip() or "legacy"

# These are the only fields covered by the canonical payload digest.  Envelope
# and transport metadata (epoch, event id, Kafka key/offset, etc.) must not
# change the domain-content hash.
DOMAIN_FIELDS = (
    "order_id",
    "customer",
    "amount",
    "country",
    "status",
    "business_version",
    "event_time",
)

CUSTOMERS = [
    "Alice",
    "Bob",
    "Charlie",
    "Daria",
    "Elena",
    "Maria",
    "Sergei",
    "Slava",
]

COUNTRIES = ["UK", "US", "ES", "IT", "DE", "FR"]
STATUSES = ["created", "paid", "shipped", "delivered"]

running = True


def stop_handler(signum: int, frame: object) -> None:
    del signum, frame
    global running
    running = False


signal.signal(signal.SIGINT, stop_handler)
signal.signal(signal.SIGTERM, stop_handler)


def delivery_report(error, message) -> None:
    if error is not None:
        print(f"Delivery failed: {error}", file=sys.stderr)
        return

    print(
        "Delivered "
        f"topic={message.topic()} "
        f"partition={message.partition()} "
        f"offset={message.offset()}"
    )


def canonical_payload_bytes(event: dict) -> bytes:
    """Return compact, UTF-8, sorted-key JSON for the domain payload."""

    domain = {field: event[field] for field in DOMAIN_FIELDS}
    return json.dumps(
        domain,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_payload_hash(payload: bytes | str | dict) -> str:
    """Hash canonical payload bytes (accepting text/event mappings for tests)."""

    if isinstance(payload, dict):
        payload = canonical_payload_bytes(payload)
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# Descriptive alias used by offline contract checks and downstream tooling.
canonicalize_payload = canonical_payload_bytes


def create_event() -> dict:
    event = {
        "order_id": str(uuid.uuid4()),
        "customer": random.choice(CUSTOMERS),
        "amount": round(random.uniform(5, 500), 2),
        "country": random.choice(COUNTRIES),
        "status": random.choice(STATUSES),
        # Domain ordering. Kafka partition/offset remains transport metadata.
        "business_version": 1,
        "event_time": datetime.now(timezone.utc).isoformat(),
    }
    payload = canonical_payload_bytes(event)
    # UUID4 is intentionally independent of order_id: retries/replays carry
    # the same event identity rather than deriving identity from transport
    # offsets or mutable business fields.
    event.update(
        {
            "source_epoch_id": SOURCE_EPOCH_ID,
            "event_id": str(uuid.uuid4()),
            "canonical_payload": payload.decode("utf-8"),
            "canonical_payload_hash": canonical_payload_hash(payload),
        }
    )
    return event


def main() -> None:
    producer = Producer(
        {
            "bootstrap.servers": BOOTSTRAP_SERVERS,
            "client.id": "orders-generator",
            "acks": "all",
            "enable.idempotence": True,
        }
    )

    delay = 1 / EVENTS_PER_SECOND

    print(
        f"Producing to {TOPIC} through {BOOTSTRAP_SERVERS}; "
        f"rate={EVENTS_PER_SECOND} events/sec"
    )

    while running:
        event = create_event()
        payload = json.dumps(event).encode("utf-8")

        producer.produce(
            topic=TOPIC,
            key=event["order_id"].encode("utf-8"),
            value=payload,
            callback=delivery_report,
        )

        producer.poll(0)
        time.sleep(delay)

    print("Flushing pending events...")
    producer.flush(10)


if __name__ == "__main__":
    main()
