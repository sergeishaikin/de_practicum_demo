from __future__ import annotations

import json
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


def create_event() -> dict:
    return {
        "order_id": str(uuid.uuid4()),
        "customer": random.choice(CUSTOMERS),
        "amount": round(random.uniform(5, 500), 2),
        "country": random.choice(COUNTRIES),
        "status": random.choice(STATUSES),
        "event_time": datetime.now(timezone.utc).isoformat(),
    }


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