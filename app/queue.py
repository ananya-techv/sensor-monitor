"""The queue: a Redis Stream.

The API only ever *adds* readings here (XADD). The worker *takes* them out later.
Because they are separate, a slow worker never slows down the API.
"""
from datetime import timezone

import redis

from app.config import REDIS_URL, STREAM
from app.schemas import Reading


def get_redis() -> redis.Redis:
    # decode_responses=True gives us normal strings instead of raw bytes.
    return redis.Redis.from_url(REDIS_URL, decode_responses=True)


def publish_reading(r, reading: Reading) -> None:
    ts = reading.timestamp
    if ts.tzinfo is None:                     # treat a time with no timezone as UTC
        ts = ts.replace(tzinfo=timezone.utc)
    r.xadd(
        STREAM,
        {"sensor_id": reading.sensor_id, "timestamp": ts.isoformat(), "value": str(reading.value)},
        maxlen=100_000,                       # safety cap so the queue can't grow forever
        approximate=True,
    )
