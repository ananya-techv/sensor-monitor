"""The web API.  Run with:  uvicorn app.main:app

Ingestion stays deliberately tiny: validate, put on the queue, answer "202 Accepted".
All the real work happens later in the worker.
"""
import asyncio
import contextlib
import logging
from pathlib import Path

import redis
import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from app import db
from app.config import ALERT_CHANNEL, GROUP, REDIS_URL, STREAM
from app.queue import get_redis, publish_reading
from app.schemas import Reading

log = logging.getLogger("api")
STATIC_DIR = Path(__file__).parent / "static"


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_schema()          # create tables on startup if they do not exist
    yield


app = FastAPI(title="Sensor Monitor", lifespan=lifespan)

_redis = get_redis()


def get_queue():
    """Dependency: lets tests swap the real Redis for a fake one."""
    return _redis


@app.post("/readings", status_code=202)
def receive_reading(reading: Reading, queue=Depends(get_queue)):
    publish_reading(queue, reading)
    return {"status": "accepted"}


@app.get("/stats")
def stats(queue=Depends(get_queue)):
    """Numbers for the dashboard header. 'backlog' = readings waiting in the queue."""
    backlog = None
    try:
        for group in queue.xinfo_groups(STREAM):
            if group["name"] == GROUP:
                backlog = group.get("lag")
    except redis.exceptions.ResponseError:
        pass                                   # stream does not exist yet (no data received)
    return {"backlog": backlog, "total_alerts": db.count_alerts()}


@app.get("/sensors")
def sensors():
    return db.latest_per_sensor()


@app.get("/sensors/{sensor_id}/readings")
def sensor_readings(sensor_id: str, limit: int = Query(100, ge=1, le=1000)):
    return db.recent_readings(sensor_id, limit)


@app.get("/alerts")
def alerts(limit: int = Query(50, ge=1, le=500)):
    return db.recent_alerts(limit)


@app.websocket("/ws/alerts")
async def ws_alerts(ws: WebSocket):
    """Push every new alert to the browser the moment the worker publishes it."""
    await ws.accept()
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe(ALERT_CHANNEL)

    async def forward():
        async for message in pubsub.listen():
            if message["type"] == "message":
                await ws.send_text(message["data"])

    forward_task = asyncio.create_task(forward())
    try:
        while True:
            await ws.receive_text()            # waits; raises WebSocketDisconnect when the tab closes
    except WebSocketDisconnect:
        pass
    finally:
        forward_task.cancel()
        await pubsub.unsubscribe(ALERT_CHANNEL)
        await pubsub.aclose()
        await r.aclose()


@app.get("/")
def dashboard():
    return FileResponse(STATIC_DIR / "index.html")
