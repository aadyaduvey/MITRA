import json
from datetime import timedelta

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from app.models import Aggregator, Collector, Material, MaterialPassport, Recycler, Transaction
from app.seed import AREAS, JAIPUR_CENTER, N_DAYS, reseed
from tests.conftest import SEED_END

CATEGORIES = {"pet", "hdpe", "paper", "glass", "metal", "ewaste"}


def test_row_counts(session):
    assert len(session.exec(select(Collector)).all()) == 40
    assert len(session.exec(select(Transaction)).all()) == 400
    assert len(session.exec(select(Aggregator)).all()) == 3
    assert len(session.exec(select(Material)).all()) == 7


def test_materials_cover_six_categories_with_prices(session):
    mats = session.exec(select(Material)).all()
    assert {m.category for m in mats} == CATEGORIES
    prices = {m.name: m.ref_price_per_kg for m in mats}
    assert prices["Copper"] == 400 and prices["Glass"] == 2


def test_every_transaction_has_valid_material_and_gps(session):
    material_ids = {m.id for m in session.exec(select(Material)).all()}
    collector_ids = {c.id for c in session.exec(select(Collector)).all()}
    lat0, lon0 = JAIPUR_CENTER
    for t in session.exec(select(Transaction)).all():
        assert t.material_id in material_ids
        assert t.collector_id in collector_ids
        assert t.gps_lat is not None and t.gps_lon is not None
        assert abs(t.gps_lat - lat0) <= 0.1 and abs(t.gps_lon - lon0) <= 0.1


def test_transactions_are_realistic(session):
    prices = {m.id: m.ref_price_per_kg for m in session.exec(select(Material)).all()}
    start = SEED_END - timedelta(days=N_DAYS)
    for t in session.exec(select(Transaction)).all():
        assert 2 <= t.weight_kg <= 50
        assert 0 < t.amount_paid <= t.weight_kg * prices[t.material_id] + 0.01
        assert start <= t.ts <= SEED_END
        assert t.aggregator_id is not None
        assert t.cv_suggested is None  # no model yet: never faked


def test_passports_chain_ends_at_authorised_recycler(session):
    passports = session.exec(select(MaterialPassport)).all()
    assert len(passports) >= 6
    recyclers = {r.id: r for r in session.exec(select(Recycler)).all()}
    for p in passports:
        tx = session.get(Transaction, p.transaction_id)
        mat = session.get(Material, tx.material_id)
        rec = recyclers[p.recycler_id]
        chain = json.loads(p.chain_json)
        assert [h["stage"] for h in chain] == ["collector", "aggregator", "recycler"]
        assert chain[0]["id"] == tx.collector_id
        assert chain[1]["id"] == tx.aggregator_id
        assert chain[2]["id"] == rec.id and chain[2]["cpcb_reg_no"] == rec.cpcb_reg_no
        assert mat.category in rec.categories.split(",")
        assert p.status in {"delivered", "in_transit"}


def test_reseed_is_deterministic_and_idempotent():
    eng = create_engine("sqlite://", poolclass=StaticPool)
    first = reseed(eng, end=SEED_END)
    with Session(eng) as s:
        snap1 = [(t.collector_id, t.material_id, t.weight_kg, t.ts) for t in s.exec(select(Transaction))]
    second = reseed(eng, end=SEED_END)
    with Session(eng) as s:
        snap2 = [(t.collector_id, t.material_id, t.weight_kg, t.ts) for t in s.exec(select(Transaction))]
    assert first == second
    assert snap1 == snap2


def test_collection_time_stays_in_window_and_hours():
    import random
    from datetime import datetime

    from app.seed import IST, collection_time

    rng = random.Random(0)
    end = datetime(2026, 9, 26, 9, 30, tzinfo=IST)  # morning reseed: no future lots
    start = end - timedelta(days=N_DAYS)
    for _ in range(500):
        ts = collection_time(rng, start, end)
        assert start <= ts <= end and 7 <= ts.hour <= 18


def test_transaction_gps_is_near_collector_area(session):
    for t in session.exec(select(Transaction)).all():
        lat, lon = AREAS[session.get(Collector, t.collector_id).area]
        assert abs(t.gps_lat - lat) <= 0.021 and abs(t.gps_lon - lon) <= 0.021
