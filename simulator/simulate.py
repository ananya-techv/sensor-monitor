"""Pretends to be a group of sensors and sends readings to the API.

Normal mode (default): every sensor sends one reading per interval, forever.
  python simulator/simulate.py

Burst mode: send N readings as fast as possible, to watch the queue fill and drain.
  python simulator/simulate.py --burst 5000

Now and then a sensor "misbehaves" on purpose (a sudden spike, or freezing on one value)
so that the anomaly detection has something to catch.
"""
import argparse
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests


def new_sensor(index: int) -> dict:
    return {"id": f"temp-{index + 1}", "base": 60 + 5 * index, "last": 60 + 5 * index,
            "stuck_left": 0, "stuck_value": 0.0}


def next_value(sensor: dict) -> float:
    if sensor["stuck_left"] > 0:                       # frozen sensor: repeats one value
        sensor["stuck_left"] -= 1
        return sensor["stuck_value"]

    roll = random.random()
    if roll < 0.01:                                    # 1%: the sensor freezes for 15 readings
        sensor["stuck_left"] = 15
        sensor["stuck_value"] = sensor["last"]
        return sensor["last"]

    normal = round(random.gauss(sensor["base"], 1.5), 1)   # usual behaviour: small wobbles
    sensor["last"] = normal
    if roll < 0.03:                                    # 2%: a sudden spike up or down
        return round(normal + random.choice([-1, 1]) * random.uniform(8, 12), 1)
    return normal


def post(session: requests.Session, url: str, payload: dict) -> None:
    try:
        response = session.post(url, json=payload, timeout=5)
        if response.status_code != 202:
            print(f"Unexpected response {response.status_code}: {response.text[:100]}")
    except requests.RequestException as exc:
        print(f"Could not reach the API ({exc.__class__.__name__}), retrying...")
        time.sleep(2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=os.getenv("API_URL", "http://127.0.0.1:8000/readings"))
    parser.add_argument("--sensors", type=int, default=5)
    parser.add_argument("--interval", type=float, default=1.0, help="seconds between rounds")
    parser.add_argument("--burst", type=int, default=0, help="send this many readings at once, then exit")
    args = parser.parse_args()

    sensors = [new_sensor(i) for i in range(args.sensors)]
    session = requests.Session()

    if args.burst:
        now = datetime.now(timezone.utc)
        payloads = []
        for i in range(args.burst):
            sensor = sensors[i % len(sensors)]
            # Slightly different timestamps, because (sensor, timestamp) must be unique in the database.
            ts = now - timedelta(milliseconds=(args.burst - i) * 5)
            payloads.append({"sensor_id": sensor["id"], "timestamp": ts.isoformat(), "value": next_value(sensor)})
        start = time.time()
        with ThreadPoolExecutor(max_workers=20) as pool:
            list(pool.map(lambda p: post(session, args.url, p), payloads))
        print(f"Sent {args.burst} readings in {time.time() - start:.1f}s")
        return

    print(f"Sending readings from {len(sensors)} sensors to {args.url} every {args.interval}s. Ctrl+C to stop.")
    while True:
        for sensor in sensors:
            payload = {
                "sensor_id": sensor["id"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "value": next_value(sensor),
            }
            post(session, args.url, payload)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
