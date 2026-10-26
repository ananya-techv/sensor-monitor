import random
import time
from datetime import datetime, timezone

import requests

URL = "http://127.0.0.1:8000/readings"
SENSORS = ["temp-1", "temp-2", "temp-3"]

while True:
    for sensor_id in SENSORS:
        reading = {
            "sensor_id": sensor_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "value": round(random.gauss(70, 2), 1),
        }
        requests.post(URL, json=reading)
    time.sleep(1)