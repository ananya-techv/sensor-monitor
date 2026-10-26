import random
from datetime import datetime, timezone

from app.detection import Detector

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def feed(detector, values, sensor_id="s1"):
    """Send values one by one; return every alert raised."""
    alerts = []
    for v in values:
        alerts.extend(detector.check(sensor_id, NOW, v))
    return alerts


def normal_values(n, seed=1):
    rng = random.Random(seed)
    return [round(rng.gauss(70, 1.5), 1) for _ in range(n)]


def test_normal_readings_raise_no_alerts():
    assert feed(Detector(), normal_values(200)) == []


def test_spike_is_detected():
    detector = Detector()
    feed(detector, normal_values(40))
    alerts = detector.check("s1", NOW, 95.0)
    assert [a.kind for a in alerts] == ["spike"]
    assert alerts[0].value == 95.0


def test_no_spike_alert_before_enough_history():
    detector = Detector(min_history=10)
    feed(detector, normal_values(5))
    assert detector.check("s1", NOW, 500.0) == []


def test_stuck_sensor_alerts_once_then_recovers():
    detector = Detector(stuck_count=10)
    feed(detector, normal_values(20))
    alerts = feed(detector, [70.0] * 25)
    assert [a.kind for a in alerts] == ["stuck"]          # one alert, not fifteen

    feed(detector, normal_values(15, seed=2))              # sensor recovers...
    again = feed(detector, [71.0] * 10)                    # ...and freezes again
    assert [a.kind for a in again] == ["stuck"]


def test_sensors_are_tracked_independently():
    detector = Detector()
    feed(detector, normal_values(40), sensor_id="a")
    # sensor "b" has no history yet, so 500 is not judged against sensor "a"
    assert detector.check("b", NOW, 500.0) == []
