"""HTTP tests via FastAPI's httpx-based TestClient. Fresh seeded in-memory DB per test."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.db import get_session
from app.main import app
from app.seed import reseed
from tests.conftest import SEED_END

RANGE = {"start": "2026-09-01", "end": "2026-09-30"}  # covers the seeded 14 days


@pytest.fixture
def client():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    reseed(eng, end=SEED_END)

    def session_override():
        with Session(eng) as s:
            yield s

    app.dependency_overrides[get_session] = session_override
    yield TestClient(app)  # no `with`: lifespan (which touches mitra.db) does not run
    app.dependency_overrides.clear()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_materials(client):
    mats = client.get("/api/materials").json()
    assert len(mats) == 7 and {"id", "name", "category", "ref_price_per_kg"} <= set(mats[0])


# ---------- collectors ----------

def test_register_collector(client):
    r = client.post("/api/collectors", json={"name": "  Asha   Devi ", "area": "Sanganer",
                                             "phone": "98290 12345"})
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == 41 and body["code"] == "MITRA-C-000041"
    assert body["name"] == "Asha Devi" and body["phone"] == "+919829012345"
    assert body["registered_ts"].endswith("+05:30")


def test_register_without_phone_and_duplicate_phone(client):
    assert client.post("/api/collectors", json={"name": "No Phone", "area": "Bagru"}).status_code == 201
    payload = {"name": "A B", "area": "X Y", "phone": "+91 9829012345"}
    assert client.post("/api/collectors", json=payload).status_code == 201
    assert client.post("/api/collectors", json=payload).status_code == 409


@pytest.mark.parametrize("bad", [{"name": "A", "area": "Sanganer"},
                                 {"name": "Asha", "area": "Sanganer", "phone": "12345"},
                                 {"name": "Asha", "area": "Sanganer", "aadhaar_last4": "12a4"}])
def test_register_validation(client, bad):
    assert client.post("/api/collectors", json=bad).status_code == 422


def test_list_and_get_collector(client):
    rows = client.get("/api/collectors").json()
    assert len(rows) == 40 and sum(r["lots"] for r in rows) == 400
    detail = client.get("/api/collectors/1").json()
    assert detail["code"] == "MITRA-C-000001"
    assert 0 < len(detail["recent_transactions"]) <= 10
    ts = [t["ts"] for t in detail["recent_transactions"]]
    assert ts == sorted(ts, reverse=True)
    assert client.get("/api/collectors/9999").status_code == 404


def test_collector_with_no_transactions(client):
    cid = client.post("/api/collectors", json={"name": "New Kabadi", "area": "Bagru"}).json()["id"]
    d = client.get(f"/api/collectors/{cid}").json()
    assert d["lots"] == 0 and d["kg"] == 0 and d["recent_transactions"] == [] and d["last_lat"] is None


# ---------- transactions ----------

def test_log_transaction_prices_at_reference(client):
    r = client.post("/api/transactions", json={"collector_id": 1, "material_id": 6, "weight_kg": 2.5,
                                               "gps_lat": 26.91, "gps_lon": 75.79})
    assert r.status_code == 201
    t = r.json()
    assert t["material"] == "Copper" and t["ref_price_per_kg"] == 400
    assert t["amount_paid"] == 1000.0 == t["ref_amount"]
    assert t["passport_id"] == "MITRA-P-000401" and t["passport_status"] == "collected"
    assert t["ts"].endswith("+05:30")
    # shows up for the map and on the collector
    assert t["id"] in {row["id"] for row in client.get("/api/transactions", params={"collector_id": 1}).json()}
    assert client.get(f"/api/passport/{t['id']}").json()["gps"] == {"lat": 26.91, "lon": 75.79}


def test_log_transaction_keeps_cv_suggestion_separate_from_confirmed_material(client):
    t = client.post("/api/transactions", json={"collector_id": 2, "material_id": 1, "weight_kg": 3,
                                               "cv_suggested": "hdpe", "cv_confidence": 0.61,
                                               "amount_paid": 30}).json()
    assert t["material"] == "PET plastic" and t["cv_suggested"] == "hdpe"
    assert t["amount_paid"] == 30 and t["ref_amount"] == 36.0


def test_log_transaction_without_gps(client):
    r = client.post("/api/transactions", json={"collector_id": 1, "material_id": 1, "weight_kg": 1})
    assert r.status_code == 201 and r.json()["gps_lat"] is None
    assert client.get(f"/api/passport/{r.json()['id']}").json()["gps"] is None


@pytest.mark.parametrize("bad", [
    {"collector_id": 1, "material_id": 999, "weight_kg": 1},   # unknown material
    {"collector_id": 999, "material_id": 1, "weight_kg": 1},   # unknown collector
    {"collector_id": 1, "material_id": 1, "weight_kg": 0},     # non-positive weight
    {"collector_id": 1, "material_id": 1, "weight_kg": 1, "gps_lat": 26.9},  # half a GPS fix
    {"collector_id": 1, "material_id": 1, "weight_kg": 1, "aggregator_id": 99},
])
def test_log_transaction_rejects_bad_input(client, bad):
    r = client.post("/api/transactions", json=bad)
    assert r.status_code == 422, r.text


def test_list_transactions_date_filter(client):
    all_rows = client.get("/api/transactions").json()
    assert len(all_rows) == 400
    day = all_rows[0]["ts"][:10]
    same_day = client.get("/api/transactions", params={"start": day, "end": day}).json()
    assert same_day and all(r["ts"][:10] == day for r in same_day)
    assert client.get("/api/transactions", params={"start": "2026-09-30", "end": "2026-09-01"}).status_code == 422


# ---------- passport ----------

def test_passport_with_full_chain(client):
    lots = client.get("/api/epr/report", params=RANGE).json()["lots"]
    p = client.get(f"/api/passport/{lots[0]['transaction_id']}").json()
    assert [h["stage"] for h in p["chain"]] == ["collector", "aggregator", "recycler"]
    assert p["destination"]["cpcb_reg_no"].startswith("CPCB/")
    assert client.get("/api/passport/99999").status_code == 404


# ---------- EPR ----------

def test_epr_json(client):
    r = client.get("/api/epr/report", params=RANGE).json()
    active = sum(1 for c in client.get("/api/collectors").json() if c["lots"])
    assert r["totals"]["lots"] == 400 and r["totals"]["collectors"] == active == len(r["collector_ids"])
    assert len(r["lots"]) == 15
    assert all(lot["recycler_cpcb_reg_no"] for lot in r["lots"])
    kg = sum(m["kg_collected"] for m in r["by_material"])
    assert abs(kg - r["totals"]["kg_collected"]) < 0.5


def test_epr_pdf(client):
    r = client.get("/api/epr/report", params={**RANGE, "format": "pdf"})
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF") and b"%%EOF" in r.content[-64:]
    assert "mitra-epr-2026-09-01-to-2026-09-30.pdf" in r.headers["content-disposition"]


def test_epr_csv(client):
    r = client.get("/api/epr/report", params={**RANGE, "format": "csv"})
    lines = r.text.strip().splitlines()
    assert r.headers["content-type"].startswith("text/csv")
    assert lines[0].startswith("passport_id,transaction_id,collector_id") and len(lines) == 16


def test_epr_empty_range(client):
    params = {"start": "2020-01-01", "end": "2020-01-31"}
    r = client.get("/api/epr/report", params=params).json()
    assert r["totals"]["lots"] == 0 and r["lots"] == []
    pdf = client.get("/api/epr/report", params={**params, "format": "pdf"})
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_epr_bad_range(client):
    assert client.get("/api/epr/report", params={"start": "2026-09-30", "end": "2026-09-01"}).status_code == 422
    assert client.get("/api/epr/report", params={"format": "xml"}).status_code == 422


# ---------- ministry + flow ----------

def test_ministry_summary(client):
    s = client.get("/api/ministry/summary").json()
    assert s["period"] is None
    assert s["totals"]["lots"] == 400 and s["totals"]["registered_collectors"] == 40
    assert {r["material"] for r in s["metal_recovery"]["materials"]} == {
        "Copper", "Metal (steel/aluminium blended)", "E-waste"}
    assert s["by_area"] and all(a["lat"] is not None for a in s["by_area"])
    ranged = client.get("/api/ministry/summary", params=RANGE).json()
    assert ranged["period"] == RANGE and ranged["totals"]["lots"] == 400


def test_sankey(client):
    s = client.get("/api/flow/sankey").json()
    assert s["nodes"] and s["links"]
    assert {n["stage"] for n in s["nodes"]} == {"collector", "aggregator", "recycler", "pending"}
    assert s["pct_traced"] > 0
    assert len(client.get("/api/flow/sankey", params={"group_by": "collector"}).json()["nodes"]) > len(s["nodes"])


def test_cors_allows_dashboard_origin(client):
    r = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
