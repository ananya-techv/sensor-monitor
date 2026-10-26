"""The worker: queue -> anomaly check -> database -> live alerts.

Run with:  python -m app.worker

Delivery guarantee: a message is acknowledged (XACK) only AFTER it is safely stored.
If the worker crashes in between, Redis still lists the message as "pending" and the
worker re-reads it on restart. So no reading is lost. A reading may occasionally be
processed twice, which is harmless because the database ignores duplicates.
"""
import json
import logging
import time
from datetime import datetime

import redis

from app import db
from app.config import (ALERT_CHANNEL, BATCH_SIZE, GROUP, STREAM, WORKER_DELAY_SECONDS,
                        WORKER_NAME)
from app.detection import Detector
from app.queue import get_redis

log = logging.getLogger("worker")


def ensure_group(r) -> None:
    """Create the consumer group (and the stream) if they do not exist yet."""
    try:
        r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except redis.exceptions.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):       # BUSYGROUP just means "already exists"
            raise


def parse(fields: dict) -> tuple[str, datetime, float]:
    return fields["sensor_id"], datetime.fromisoformat(fields["timestamp"]), float(fields["value"])


def process_batch(r, detector: Detector, messages: list) -> int:
    rows, alerts, ids = [], [], []
    for msg_id, fields in messages:
        ids.append(msg_id)
        try:
            sensor_id, ts, value = parse(fields)
        except (KeyError, ValueError):
            log.warning("Dropping malformed message %s: %s", msg_id, fields)
            continue                          # still acknowledged below, so it is not retried forever
        rows.append((sensor_id, ts, value))
        alerts.extend(detector.check(sensor_id, ts, value))

    if rows:
        db.insert_readings(rows)
    if alerts:
        db.insert_alerts(alerts)
        for alert in alerts:
            r.publish(ALERT_CHANNEL, json.dumps(alert.to_dict()))
            log.info("ALERT %s: %s", alert.kind, alert.message)

    r.xack(STREAM, GROUP, *ids)               # only now is it safe to forget the messages
    return len(rows)


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    r = get_redis()
    db.init_schema()
    ensure_group(r)
    detector = Detector()

    # Id "0" means: first give me messages I was sent before but never acknowledged
    # (left over from a crash). Once none are left we switch to ">" (= only new messages).
    read_from = "0"
    log.info("Worker %s started", WORKER_NAME)

    while True:
        response = r.xreadgroup(GROUP, WORKER_NAME, {STREAM: read_from},
                                count=BATCH_SIZE, block=2000 if read_from == ">" else None)
        messages = response[0][1] if response else []

        if not messages:
            if read_from != ">":
                log.info("No unfinished messages left, waiting for new ones")
                read_from = ">"
            continue

        count = process_batch(r, detector, messages)
        log.info("Processed %d readings", count)
        if WORKER_DELAY_SECONDS:
            time.sleep(WORKER_DELAY_SECONDS)


if __name__ == "__main__":
    run()
