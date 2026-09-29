"""Shared links (other devices) can read everything but cannot change data."""
from app.remote import REMOTE_EDIT_DENIED

VISITOR = {"X-Forwarded-For": "49.36.12.7, 127.0.0.1"}  # phone on another network, via the proxy
TUNNEL = {"Cf-Connecting-Ip": "49.36.12.7"}
LOCAL = {"X-Forwarded-For": "::ffff:127.0.0.1"}  # the laptop's own browser, via the proxy


def test_remote_visitors_can_read(client):
    for headers in (VISITOR, TUNNEL):
        assert client.get("/api/ministry/summary", headers=headers).status_code == 200
        assert client.get("/api/epr/report", params={"format": "pdf"}, headers=headers).status_code == 200


def test_remote_visitors_cannot_change_data(client):
    for headers in (VISITOR, TUNNEL):
        r = client.put("/api/prices/1", json={"ref_price_per_kg": 1, "source": "hacker"}, headers=headers)
        assert r.status_code == 403 and r.json()["detail"] == REMOTE_EDIT_DENIED
        assert client.delete("/api/collectors/1", headers=headers).status_code == 403
        assert client.post("/api/prices/live", headers=headers).status_code == 403
    assert client.get("/api/collectors/1").json()["name"] != "Erased collector"


def test_laptop_and_bot_can_still_change_data(client):
    assert client.put("/api/prices/1", json={"ref_price_per_kg": 13, "source": "rate card"},
                      headers=LOCAL).status_code == 200
    assert client.post("/api/collectors", json={"name": "Bot User", "area": "Sanganer"}).status_code == 201


def test_remote_edits_can_be_allowed(client, monkeypatch):
    monkeypatch.setenv("MITRA_REMOTE_EDITS", "1")
    r = client.put("/api/prices/1", json={"ref_price_per_kg": 13, "source": "rate card"}, headers=VISITOR)
    assert r.status_code == 200
