from fastapi.testclient import TestClient

from app.main import app, get_queue


class FakeQueue:
    """Stands in for Redis and just remembers what was added."""

    def __init__(self):
        self.added = []

    def xadd(self, stream, fields, **kwargs):
        self.added.append((stream, fields))


def make_client():
    fake = FakeQueue()
    app.dependency_overrides[get_queue] = lambda: fake
    # No "with" block: that would run startup code which needs a real database.
    return TestClient(app), fake


def teardown_function():
    app.dependency_overrides.clear()


def test_valid_reading_is_accepted_and_queued():
    client, fake = make_client()
    response = client.post("/readings", json={
        "sensor_id": "temp-1", "timestamp": "2026-01-01T10:00:00Z", "value": 71.5})
    assert response.status_code == 202
    assert len(fake.added) == 1
    assert fake.added[0][1]["sensor_id"] == "temp-1"
    assert fake.added[0][1]["value"] == "71.5"


def test_timestamp_without_timezone_is_stored_as_utc():
    client, fake = make_client()
    client.post("/readings", json={"sensor_id": "t", "timestamp": "2026-01-01T10:00:00", "value": 1})
    assert fake.added[0][1]["timestamp"].endswith("+00:00")


def test_bad_value_is_rejected_and_not_queued():
    client, fake = make_client()
    response = client.post("/readings", json={
        "sensor_id": "temp-1", "timestamp": "2026-01-01T10:00:00Z", "value": "hello"})
    assert response.status_code == 422
    assert fake.added == []


def test_missing_field_is_rejected():
    client, fake = make_client()
    response = client.post("/readings", json={"sensor_id": "temp-1", "value": 5})
    assert response.status_code == 422
    assert fake.added == []


def test_empty_sensor_id_is_rejected():
    client, fake = make_client()
    response = client.post("/readings", json={
        "sensor_id": "", "timestamp": "2026-01-01T10:00:00Z", "value": 5})
    assert response.status_code == 422
