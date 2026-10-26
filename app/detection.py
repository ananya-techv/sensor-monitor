"""Anomaly detection.

This file knows nothing about Redis, Postgres or HTTP. It just receives readings
and says whether they look wrong. That makes it easy to test and easy to extend.

Rules:
  1. spike - the value is far from the sensor's recent average (z-score).
     Threshold 4 (not the textbook 3): with 3, ordinary noise would trigger a false
     alarm roughly once per 370 readings per sensor, which is too noisy to be useful.
  2. stuck - the sensor repeats exactly the same value many times in a row.
"""
import statistics
from collections import deque
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Alert:
    sensor_id: str
    timestamp: datetime
    kind: str
    message: str
    value: float

    def to_dict(self) -> dict:
        return {
            "sensor_id": self.sensor_id,
            "ts": self.timestamp.isoformat(),
            "kind": self.kind,
            "message": self.message,
            "value": self.value,
        }


class _SensorState:
    """What we remember about one sensor between readings."""

    def __init__(self, window: int):
        self.values = deque(maxlen=window)   # only the most recent `window` values are kept
        self.stuck_alerted = False           # so one frozen sensor raises ONE alert, not hundreds


class Detector:
    def __init__(self, window=30, z_threshold=4.0, min_history=10, stuck_count=10):
        self.window = window
        self.z_threshold = z_threshold
        self.min_history = min_history
        self.stuck_count = stuck_count
        self._states: dict[str, _SensorState] = {}

    def check(self, sensor_id: str, timestamp: datetime, value: float) -> list[Alert]:
        state = self._states.setdefault(sensor_id, _SensorState(self.window))
        alerts: list[Alert] = []

        # Rule 1: spike. Compare the new value with the history BEFORE adding it,
        # otherwise the spike would pollute its own average.
        if len(state.values) >= self.min_history:
            mean = statistics.fmean(state.values)
            std = statistics.pstdev(state.values)
            if std > 1e-9:                    # std == 0 means "all identical": the stuck rule handles that
                z = (value - mean) / std
                if abs(z) > self.z_threshold:
                    alerts.append(Alert(
                        sensor_id, timestamp, "spike",
                        f"{sensor_id} read {value:g}, which is {abs(z):.1f} standard deviations "
                        f"from its recent average of {mean:.1f}",
                        value,
                    ))

        state.values.append(value)

        # Rule 2: stuck. The last `stuck_count` values are all identical.
        recent = list(state.values)[-self.stuck_count:]
        is_stuck = len(recent) == self.stuck_count and len(set(recent)) == 1
        if is_stuck and not state.stuck_alerted:
            state.stuck_alerted = True
            alerts.append(Alert(
                sensor_id, timestamp, "stuck",
                f"{sensor_id} has sent the same value ({value:g}) {self.stuck_count} times in a row",
                value,
            ))
        elif not is_stuck:
            state.stuck_alerted = False       # sensor recovered, allow a future stuck alert

        return alerts
