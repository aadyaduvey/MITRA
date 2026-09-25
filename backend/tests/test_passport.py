import hashlib
import json
from datetime import datetime, timezone

from sqlmodel import select

from app.engine.loaders import flow_records, passport_for
from app.engine.passport import build_passport, photo_hash
from app.models import Aggregator, Collector, Material, MaterialPassport, Recycler, Transaction

TS = datetime(2026, 9, 20, 5, 0, tzinfo=timezone.utc)
COLLECTOR = Collector(id=7, name="Asha Devi", phone="+910000000000", area="Sanganer",
                      aadhaar_last4="1234", registered_ts=TS)
MATERIAL = Material(id=3, name="Copper", category="metal", ref_price_per_kg=400)
AGG = Aggregator(id=1, name="Agg One", area="Sanganer", cpcb_reg_no="AGG-1")
REC = Recycler(id=2, name="Rec Two", area="VKI", cpcb_reg_no="CPCB-2", categories="metal")
TX = Transaction(id=42, collector_id=7, material_id=3, weight_kg=2.5, amount_paid=950.0,
                 gps_lat=26.82, gps_lon=75.79, ts=TS, aggregator_id=1)
CHAIN = [{"stage": "collector", "id": 7}, {"stage": "aggregator", "id": 1},
         {"stage": "recycler", "id": 2, "cpcb_reg_no": "CPCB-2"}]
MP = MaterialPassport(id=1, transaction_id=42, chain_json=json.dumps(CHAIN), recycler_id=2,
                      status="delivered")


def test_full_chain_passport():
    p = build_passport(TX, COLLECTOR, MATERIAL, AGG, MP, REC, photo_sha256="abc")
    assert p["passport_id"] == "MITRA-P-000042"
    assert p["status"] == "delivered" and p["custody_complete"] is True
    assert [h["stage"] for h in p["chain"]] == ["collector", "aggregator", "recycler"]
    assert p["destination"] == {"recycler_id": 2, "name": "Rec Two", "cpcb_reg_no": "CPCB-2"}
    assert p["gps"] == {"lat": 26.82, "lon": 75.79}
    assert p["material"]["category"] == "metal" and p["weight_kg"] == 2.5
    assert p["classification"]["confirmed_by"] == "collector"
    json.dumps(p)  # serialisable


def test_passport_never_leaks_phone_or_aadhaar():
    text = json.dumps(build_passport(TX, COLLECTOR, MATERIAL, AGG, MP, REC))
    assert COLLECTOR.phone not in text and "aadhaar" not in text


def test_passport_without_downstream_chain():
    p = build_passport(TX, COLLECTOR, MATERIAL, AGG)
    assert p["status"] == "collected" and p["custody_complete"] is False
    assert [h["stage"] for h in p["chain"]] == ["collector", "aggregator"]
    assert p["chain"][1]["ts"] is None
    assert p["destination"] is None


def test_passport_without_gps():
    tx = TX.model_copy(update={"gps_lat": None, "gps_lon": None})
    assert build_passport(tx, COLLECTOR, MATERIAL)["gps"] is None


def test_photo_hash():
    assert photo_hash(b"img") == hashlib.sha256(b"img").hexdigest()
    assert photo_hash(None) is None and photo_hash(b"") is None


# --- loaders against the seeded in-memory DB ---

def test_passport_for_seeded_transaction(session):
    mp = session.exec(select(MaterialPassport)).first()
    p = passport_for(session, mp.transaction_id)
    assert p["chain"][-1]["stage"] == "recycler"
    assert p["destination"]["cpcb_reg_no"].startswith("CPCB/")
    assert passport_for(session, 999_999) is None


def test_flow_records_cover_all_seeded_kg(session):
    records = flow_records(session)
    total = sum(t.weight_kg for t in session.exec(select(Transaction)))
    assert len(records) == 400
    assert round(sum(r.kg for r in records), 1) == round(total, 1)
    assert sum(1 for r in records if r.recycler) == len(session.exec(select(MaterialPassport)).all())
    assert len({r.collector for r in flow_records(session, group_by="area")}) <= 15


def test_passport_timestamps_are_ist():
    p = build_passport(TX, COLLECTOR, MATERIAL, AGG)
    assert p["collected_at"] == "2026-09-20T10:30:00+05:30"  # 05:00 UTC
    assert p["chain"][0]["ts"] == p["collected_at"]
