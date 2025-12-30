# tests/test_workouts.py
import httpx
import pytest

from app.main import user_service_breaker


def workout_payload(user_id=1):
    return {
        "user_id": user_id,
        "workout_type": "Run",
        "duration_minutes": 30,
        "calories": 250,
        "workout_date": "2025-12-30",
        "notes": "Easy run",
    }


def test_create_workout_user_ok(client, monkeypatch):
    # NEW: Mock users_service returning 200 OK
    def fake_get(self, url, *args, **kwargs):
        class Resp:
            status_code = 200
        return Resp()

    monkeypatch.setattr(httpx.Client, "get", fake_get)

    r = client.post("/workouts", json=workout_payload(user_id=1))
    assert r.status_code == 201
    data = r.json()
    assert data["user_id"] == 1
    assert data["workout_type"] == "Run"


def test_create_workout_user_not_found(client, monkeypatch):
    # NEW: Mock users_service returning 404
    def fake_get(self, url, *args, **kwargs):
        class Resp:
            status_code = 404
        return Resp()

    monkeypatch.setattr(httpx.Client, "get", fake_get)

    r = client.post("/workouts", json=workout_payload(user_id=999))
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


def test_create_workout_user_service_down(client, monkeypatch):
    # NEW: Mock users_service raising a network/timeout error
    def fake_get(self, url, *args, **kwargs):
        raise httpx.RequestError("boom")

    monkeypatch.setattr(httpx.Client, "get", fake_get)

    r = client.post("/workouts", json=workout_payload(user_id=1))
    assert r.status_code == 503
    assert "unavailable" in r.json()["detail"].lower()


def test_circuit_breaker_opens_on_repeated_failures(client, monkeypatch):
    # NEW: Reset breaker state for test stability
    user_service_breaker.close()

    # Force repeated RequestError to trip breaker
    def fake_get(self, url, *args, **kwargs):
        raise httpx.RequestError("boom")

    monkeypatch.setattr(httpx.Client, "get", fake_get)

    # 1st failure
    r1 = client.post("/workouts", json=workout_payload(user_id=1))
    assert r1.status_code == 503

    # 2nd failure
    r2 = client.post("/workouts", json=workout_payload(user_id=1))
    assert r2.status_code == 503

    # 3rd failure should open the circuit (with fail_max=3)
    r3 = client.post("/workouts", json=workout_payload(user_id=1))
    assert r3.status_code == 503

    # Next call should be fast fallback with "circuit open" message
    r4 = client.post("/workouts", json=workout_payload(user_id=1))
    assert r4.status_code == 503
    assert "circuit" in r4.json()["detail"].lower()
