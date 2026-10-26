"""Settings shared by the API and the worker.

Every value can be overridden with an environment variable, which is how
Docker Compose (and any hosting platform) configures the app without code changes.
"""
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://sensor:sensor@localhost:5432/sensors")

STREAM = "readings"          # the queue: a Redis Stream holding incoming readings
GROUP = "workers"            # consumer group: lets several workers share the queue safely
ALERT_CHANNEL = "alerts"     # Redis pub/sub channel used to push alerts to dashboards

WORKER_NAME = os.getenv("WORKER_NAME", "worker-1")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "100"))
# Artificial slowdown (seconds per batch). Only for demos: it lets you watch the queue fill up.
WORKER_DELAY_SECONDS = float(os.getenv("WORKER_DELAY_SECONDS", "0"))
