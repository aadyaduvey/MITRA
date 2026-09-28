"""Reference prices: price file, manual updates, frozen receipts, DB upgrade, live feed, API, CLI.
No network: the live feed is tested against a fake MetalpriceAPI response."""
import csv
from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from app.bot import messages as msg
from app.db import add_missing_columns
from app.engine import pricing
from app.models import IST, Material, PriceUpdate
from app.prices import live
from app.prices.__main__ import main as prices_cli
from app.prices.service import PriceError, find_material, history, set_price
from app.seed import reseed
from tests.conftest import SEED_END

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=IST)


@pytest.fixture
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    reseed(eng, end=SEED_END)
    return eng


# ---------- price file ----------

def test_price_file_has_source_columns_and_save_keeps_other_rows():
    prices = pricing.load_prices()
    assert prices["Copper"].source.startswith("Indicative")
    pricing.save_price("Copper", 780, "Jaipur kabadi market", "2026-09-28")
    rows = list(csv.DictReader(pricing.PRICES_CSV.open(encoding="utf-8")))
    assert list(rows[0]) == pricing.CSV_FIELDS
    copper = next(r for r in rows if r["material"] == "Copper")
    assert (copper["ref_price_per_kg"], copper["source"], copper["updated_on"]) == ("780", "Jaipur kabadi market", "2026-09-28")
    assert next(r for r in rows if r["material"] == "Glass")["ref_price_per_kg"] == "2"
    assert len(rows) == 7


def test_old_price_file_without_source_columns_still_loads():
    rows = [{"material": "Copper", "category": "metal", "ref_price_per_kg": "400"}]
    assert pricing.parse_prices(rows)["Copper"].source == ""


# ---------- manual updates ----------

def test_find_material(db):
    with Session(db) as s:
        assert find_material(s, "copper").name == "Copper"
        assert find_material(s, "cop").name == "Copper"
        assert find_material(s, "Metal (steel/aluminium blended)").category == "metal"
        assert find_material(s, str(find_material(s, "Glass").id)).name == "Glass"
        with pytest.raises(PriceError, match="several"):
            find_material(s, "c")  # Cardboard/paper and Copper
        with pytest.raises(PriceError, match="no material"):
            find_material(s, "gold")


def test_set_price_updates_material_history_and_file(db):
    with Session(db) as s:
        copper = find_material(s, "Copper")
        u = set_price(s, copper, 780, "  Jaipur   kabadi market ", now=NOW)
        assert (u.previous_price, u.price_per_kg, u.source) == (400, 780, "Jaipur kabadi market")
        assert s.get(Material, copper.id).ref_price_per_kg == 780
        assert history(s, copper.id)[0].price_per_kg == 780
        assert pricing.load_prices()["Copper"].ref_price_per_kg == 780
        for bad_price in (0, -5, 200_000):
            with pytest.raises(PriceError):
                set_price(s, copper, bad_price, "x source")
        with pytest.raises(PriceError, match="source"):
            set_price(s, copper, 700, " ")


def test_seed_records_where_starting_prices_came_from(db):
    with Session(db) as s:
        rows = s.exec(select(PriceUpdate)).all()
        assert len(rows) == 7 and all(r.source.startswith("Indicative") for r in rows)


# ---------- receipts stay as they were ----------

def test_price_change_does_not_rewrite_past_receipts(client):
    copper = next(m for m in client.get("/api/materials").json() if m["name"] == "Copper")
    old = client.post("/api/transactions", json={"collector_id": 1, "material_id": copper["id"], "weight_kg": 2}).json()
    assert old["ref_price_per_kg"] == 400 and old["ref_amount"] == 800

    r = client.put(f"/api/prices/{copper['id']}", json={"ref_price_per_kg": 780, "source": "Jaipur kabadi market"})
    assert r.status_code == 200 and r.json()["ref_price_per_kg"] == 780

    new = client.post("/api/transactions", json={"collector_id": 1, "material_id": copper["id"], "weight_kg": 2}).json()
    assert new["ref_price_per_kg"] == 780 and new["ref_amount"] == 1560
    again = {t["id"]: t for t in client.get("/api/transactions", params={"collector_id": 1}).json()}[old["id"]]
    assert again["ref_price_per_kg"] == 400 and again["ref_amount"] == 800
    assert client.get(f"/api/passport/{old['id']}").json()["material"]["ref_price_per_kg"] == 400


# ---------- database upgrade ----------

def test_old_database_gets_new_columns_without_reseed(tmp_path):
    eng = create_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    with eng.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE "transaction" (id INTEGER PRIMARY KEY, weight_kg FLOAT NOT NULL)')
    added = add_missing_columns(eng)
    assert "transaction.ref_price_per_kg" in added
    with eng.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql('PRAGMA table_info("transaction")')}
    assert "ref_price_per_kg" in cols
    assert add_missing_columns(eng) == []  # second run: nothing to do


# ---------- live metal feed ----------

def fake_provider(payload: dict, calls: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        return httpx.Response(200, json=payload)
    return httpx.Client(transport=httpx.MockTransport(handler))


# about Rs 852.6/kg copper: Rs 24.17 per ounce x 35.274 ounces per kg
GOOD = {"success": True, "base": "INR", "timestamp": 1790000000, "rates": {"XCU": 1 / 24.17, "INRXCU": 24.17}}


def test_fetch_and_price_formula():
    calls = []
    per_kg = live.fetch_inr_per_kg(["XCU"], "k", fake_provider(GOOD, calls))
    assert per_kg["XCU"] == pytest.approx(24.17 * live.OZ_PER_KG)
    q = calls[0].url.params
    assert (q["api_key"], q["base"], q["currencies"]) == ("k", "INR", "XCU")
    rule = live.LIVE_RULES["Copper"]
    assert live.reference_price(rule, 852.6) == round(852.6 * 0.9 * 0.9)  # Rs 691/kg
    only_inverse = {"success": True, "rates": {"XCU": 1 / 24.17}}
    assert live.fetch_inr_per_kg(["XCU"], "k", fake_provider(only_inverse))["XCU"] == pytest.approx(852.6, abs=0.1)


def test_refresh_live_updates_copper_only(db):
    with Session(db) as s:
        out = live.refresh_live(s, key="k", client=fake_provider(GOOD), now=NOW)
        assert out["configured"]
        [r] = out["results"]
        assert r["material"] == "Copper" and r["status"] == "updated" and r["new_price"] == 691
        assert find_material(s, "Copper").ref_price_per_kg == 691
        assert find_material(s, "Glass").ref_price_per_kg == 2  # no feed: unchanged
        assert history(s, find_material(s, "Copper").id)[0].source.startswith("Live: MetalpriceAPI XCU")


def test_refresh_live_rejects_unbelievable_price(db):
    wrong_unit = {"success": True, "rates": {"INRXCU": 2417.0}}  # 100x too high: kept, not saved
    with Session(db) as s:
        [r] = live.refresh_live(s, key="k", client=fake_provider(wrong_unit), now=NOW)["results"]
        assert r["status"] == "rejected" and find_material(s, "Copper").ref_price_per_kg == 400


def test_refresh_live_keeps_last_price_on_errors(db):
    refused = {"success": False, "error": {"statusCode": 101, "info": "Invalid API key"}}

    def offline(request):
        raise httpx.ConnectError("no internet", request=request)

    with Session(db) as s:
        [r] = live.refresh_live(s, key="bad", client=fake_provider(refused), now=NOW)["results"]
        assert r["status"] == "kept" and "Invalid API key" in r["detail"]
        [r] = live.refresh_live(s, key="k", client=httpx.Client(transport=httpx.MockTransport(offline)))["results"]
        assert r["status"] == "kept" and "not reachable" in r["detail"]
        assert find_material(s, "Copper").ref_price_per_kg == 400


def test_refresh_live_without_key(db):
    with Session(db) as s:
        out = live.refresh_live(s)
    assert out == {"configured": False, "results": [], "message": out["message"]}
    assert live.KEY_NAME in out["message"]


def test_refresh_if_stale(db, monkeypatch):
    monkeypatch.setenv(live.KEY_NAME, "k")
    with Session(db) as s:
        live.refresh_live(s, key="k", client=fake_provider(GOOD), now=NOW)
        assert live.refresh_if_stale(s, now=NOW + timedelta(hours=2)) is None  # fresh: no call


# ---------- API ----------

def test_price_board_and_history(client):
    board = client.get("/api/prices").json()
    assert board["live_configured"] is False and board["live_provider"] == "MetalpriceAPI"
    copper = next(p for p in board["prices"] if p["name"] == "Copper")
    assert copper["live"] and "XCU" in copper["live_rule"] and copper["price_source"].startswith("Indicative")
    assert next(p for p in board["prices"] if p["name"] == "Glass")["live"] is False

    client.put(f"/api/prices/{copper['id']}", json={"ref_price_per_kg": 760, "source": "Aggregator rate card"})
    mats = {m["name"]: m for m in client.get("/api/materials").json()}
    assert mats["Copper"]["ref_price_per_kg"] == 760 and mats["Copper"]["price_source"] == "Aggregator rate card"
    h = client.get("/api/prices/history", params={"material_id": copper["id"]}).json()
    assert h[0]["price_per_kg"] == 760 and h[0]["previous_price"] == 400 and h[0]["ts"].endswith("+05:30")


def test_price_api_validation(client):
    assert client.put("/api/prices/1", json={"ref_price_per_kg": 0, "source": "x y"}).status_code == 422
    assert client.put("/api/prices/1", json={"ref_price_per_kg": 10}).status_code == 422  # source required
    assert client.put("/api/prices/999", json={"ref_price_per_kg": 10, "source": "x y"}).status_code == 404
    r = client.post("/api/prices/live").json()
    assert r["configured"] is False and r["results"] == []


# ---------- terminal command ----------

def test_cli(db, capsys):
    assert prices_cli([], bind=db) == 0
    assert "Copper" in capsys.readouterr().out
    assert prices_cli(["set", "cop", "780", "--source", "Jaipur kabadi market"], bind=db) == 0
    assert "Rs 400.00 -> Rs 780.00/kg" in capsys.readouterr().out
    assert prices_cli(["set", "c", "10", "--source", "x y"], bind=db) == 2  # ambiguous name
    assert prices_cli(["history", "Copper"], bind=db) == 0
    assert "Jaipur kabadi market" in capsys.readouterr().out
    assert prices_cli(["live"], bind=db) == 1  # no key: explains how to set one


# ---------- bot shows how fresh the prices are ----------

def test_bot_price_list_shows_update_date():
    mats = [{"name": "Copper", "ref_price_per_kg": 780.0, "price_updated_at": "2026-09-28T10:00:00+05:30"},
            {"name": "Glass", "ref_price_per_kg": 2.0, "price_updated_at": "2026-09-01T10:00:00+05:30"}]
    assert "Prices updated: 28/09/2026" in msg.prices(mats)
    assert "भाव अपडेट: 28/09/2026" in msg.prices(mats, "hi")
    assert "updated" not in msg.prices([{"name": "Glass", "ref_price_per_kg": 2.0}])


def test_old_database_gets_starting_price_history():
    from app.prices.service import ensure_price_history
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    reseed(eng, end=SEED_END)
    with Session(eng) as s:
        for row in s.exec(select(PriceUpdate)):
            s.delete(row)  # simulate a database from before price history existed
        s.commit()
        assert ensure_price_history(s, now=NOW) == 7
        assert ensure_price_history(s, now=NOW) == 0  # only once
        assert {u.source for u in history(s)} == {"Indicative FY24-25 estimate (PoC default)"}
