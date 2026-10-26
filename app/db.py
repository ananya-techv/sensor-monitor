"""PostgreSQL access. All SQL lives in this one file."""
import contextlib
import logging
import time

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from psycopg2.pool import ThreadedConnectionPool

from app.config import DATABASE_URL

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id        BIGSERIAL PRIMARY KEY,
    sensor_id TEXT             NOT NULL,
    ts        TIMESTAMPTZ      NOT NULL,
    value     DOUBLE PRECISION NOT NULL,
    UNIQUE (sensor_id, ts)          -- also builds the index that makes per-sensor lookups fast
);

CREATE TABLE IF NOT EXISTS alerts (
    id        BIGSERIAL PRIMARY KEY,
    sensor_id TEXT        NOT NULL,
    ts        TIMESTAMPTZ NOT NULL,
    kind      TEXT        NOT NULL,
    message   TEXT        NOT NULL,
    value     DOUBLE PRECISION,
    UNIQUE (sensor_id, ts, kind)
);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts (ts DESC);
"""

_pool = None


def _get_pool() -> ThreadedConnectionPool:
    """Create the connection pool, waiting for the database to come up if needed."""
    global _pool
    if _pool is None:
        for attempt in range(30):
            try:
                _pool = ThreadedConnectionPool(1, 10, DATABASE_URL)
                break
            except psycopg2.OperationalError:
                log.info("Waiting for the database (attempt %d)...", attempt + 1)
                time.sleep(1)
        else:
            raise RuntimeError("Could not connect to the database")
    return _pool


@contextlib.contextmanager
def connection():
    """Borrow a connection from the pool; commit on success, roll back on error."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def init_schema() -> None:
    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(42)")   # API and worker may start together: take turns
        cur.execute(SCHEMA)


def insert_readings(rows: list[tuple]) -> None:
    """rows = [(sensor_id, ts, value), ...]. Duplicates are skipped, which makes retries safe."""
    with connection() as conn, conn.cursor() as cur:
        execute_values(
            cur,
            "INSERT INTO readings (sensor_id, ts, value) VALUES %s ON CONFLICT DO NOTHING",
            rows,
        )


def insert_alerts(alerts) -> None:
    rows = [(a.sensor_id, a.timestamp, a.kind, a.message, a.value) for a in alerts]
    with connection() as conn, conn.cursor() as cur:
        execute_values(
            cur,
            "INSERT INTO alerts (sensor_id, ts, kind, message, value) VALUES %s ON CONFLICT DO NOTHING",
            rows,
        )


def recent_alerts(limit: int = 50) -> list[dict]:
    with connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT sensor_id, ts, kind, message, value FROM alerts ORDER BY ts DESC LIMIT %s",
            (limit,),
        )
        return cur.fetchall()


def recent_readings(sensor_id: str, limit: int = 100) -> list[dict]:
    with connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT sensor_id, ts, value FROM readings WHERE sensor_id = %s ORDER BY ts DESC LIMIT %s",
            (sensor_id, limit),
        )
        return cur.fetchall()


def latest_per_sensor() -> list[dict]:
    """Newest reading of every sensor, plus how many alerts it raised in the last 5 minutes."""
    with connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT r.sensor_id, r.ts, r.value,
                   (SELECT count(*) FROM alerts a
                     WHERE a.sensor_id = r.sensor_id
                       AND a.ts > now() - interval '5 minutes') AS recent_alerts
            FROM (SELECT DISTINCT ON (sensor_id) sensor_id, ts, value
                    FROM readings ORDER BY sensor_id, ts DESC) r
            ORDER BY r.sensor_id
            """
        )
        return cur.fetchall()


def count_alerts() -> int:
    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM alerts")
        return cur.fetchone()[0]
