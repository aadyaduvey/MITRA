"""DB -> plain engine inputs. The only engine module that touches a Session."""
import json
from datetime import datetime
from typing import Literal

from sqlmodel import Session, func, select

from app.engine.epr import EprLot
from app.engine.material_flow import FlowRecord
from app.engine.passport import build_passport, ist, passport_id
from app.engine.summary import Lot
from app.models import Aggregator, Collector, Material, MaterialPassport, Recycler, Transaction


def transactions_between(session: Session, start: datetime | None = None,
                         end: datetime | None = None) -> list[Transaction]:
    """Transactions with start <= ts <= end (either bound optional), oldest first."""
    q = select(Transaction)
    if start is not None:
        q = q.where(Transaction.ts >= start)
    if end is not None:
        q = q.where(Transaction.ts <= end)
    return list(session.exec(q.order_by(Transaction.ts, Transaction.id)))


def _lookups(session: Session) -> dict[str, dict]:
    return {
        "collectors": {c.id: c for c in session.exec(select(Collector))},
        "materials": {m.id: m for m in session.exec(select(Material))},
        "aggregators": {a.id: a for a in session.exec(select(Aggregator))},
        "recyclers": {r.id: r for r in session.exec(select(Recycler))},
        "passports": {p.transaction_id: p for p in session.exec(select(MaterialPassport))},
    }


def flow_records(session: Session, group_by: Literal["collector", "area"] = "collector",
                 start: datetime | None = None, end: datetime | None = None) -> list[FlowRecord]:
    lk = _lookups(session)
    records = []
    for tx in transactions_between(session, start, end):
        if tx.aggregator_id is None:
            continue  # not yet sold on: no flow to draw
        c = lk["collectors"][tx.collector_id]
        mp = lk["passports"].get(tx.id)
        rec = lk["recyclers"].get(mp.recycler_id) if mp else None
        records.append(FlowRecord(
            collector=c.area if group_by == "area" else f"{c.name} (#{c.id})",
            aggregator=lk["aggregators"][tx.aggregator_id].name,
            recycler=rec.name if rec else None,
            material=lk["materials"][tx.material_id].category,
            kg=tx.weight_kg,
            material_name=lk["materials"][tx.material_id].name,
        ))
    return records


def epr_lots(session: Session, start: datetime, end: datetime) -> list[EprLot]:
    lk = _lookups(session)
    lots = []
    for tx in transactions_between(session, start, end):
        mat = lk["materials"][tx.material_id]
        mp = lk["passports"].get(tx.id)
        rec = lk["recyclers"].get(mp.recycler_id) if mp else None
        agg = lk["aggregators"].get(tx.aggregator_id)
        delivered_at = None
        if mp is not None and mp.status == "delivered":
            delivered_at = json.loads(mp.chain_json)[-1].get("ts")
        lots.append(EprLot(
            passport_id=passport_id(tx.id),
            transaction_id=tx.id,
            collector_id=tx.collector_id,
            collected_at=ist(tx.ts),
            material=mat.name,
            category=mat.category,
            kg=tx.weight_kg,
            aggregator=agg.name if agg else None,
            recycler=rec.name if rec else None,
            recycler_cpcb_reg_no=rec.cpcb_reg_no if rec else None,
            status=mp.status if mp else "collected",
            delivered_at=delivered_at,
        ))
    return lots


def summary_lots(session: Session, start: datetime | None = None,
                 end: datetime | None = None) -> list[Lot]:
    lk = _lookups(session)
    lots = []
    for tx in transactions_between(session, start, end):
        mat = lk["materials"][tx.material_id]
        mp = lk["passports"].get(tx.id)
        lots.append(Lot(
            collector_id=tx.collector_id,
            area=lk["collectors"][tx.collector_id].area,
            material=mat.name,
            category=mat.category,
            kg=tx.weight_kg,
            ref_price_per_kg=mat.ref_price_per_kg,
            amount_paid=tx.amount_paid,
            lat=tx.gps_lat,
            lon=tx.gps_lon,
            traced=mp is not None and mp.recycler_id is not None,
        ))
    return lots


def collector_count(session: Session) -> int:
    return session.exec(select(func.count()).select_from(Collector)).one()


def passport_for(session: Session, transaction_id: int) -> dict | None:
    tx = session.get(Transaction, transaction_id)
    if tx is None:
        return None
    mp = session.exec(
        select(MaterialPassport).where(MaterialPassport.transaction_id == tx.id)
    ).first()
    return build_passport(
        tx,
        collector=session.get(Collector, tx.collector_id),
        material=session.get(Material, tx.material_id),
        aggregator=session.get(Aggregator, tx.aggregator_id) if tx.aggregator_id else None,
        passport=mp,
        recycler=session.get(Recycler, mp.recycler_id) if mp and mp.recycler_id else None,
    )
