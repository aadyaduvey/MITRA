"""Shared helpers for routers: session dependency, date ranges, ORM -> schema."""
from datetime import date, datetime, time, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlmodel import Session, select

from app.db import get_session
from app.engine.passport import passport_id
from app.engine.pricing import quote
from app.models import IST, Collector, Material, MaterialPassport, Transaction
from app.schemas import CollectorOut, MaterialOut, TransactionOut

SessionDep = Annotated[Session, Depends(get_session)]


def today_ist() -> date:
    return datetime.now(IST).date()


def day_bounds(start: date | None, end: date | None) -> tuple[datetime | None, datetime | None]:
    """Inclusive IST calendar days -> aware datetimes [start 00:00, end 23:59:59.999999].

    A missing end stays None (open range).
    """
    if start and end and start > end:
        raise HTTPException(422, f"start ({start}) is after end ({end})")
    lo = datetime.combine(start, time.min, IST) if start else None
    hi = datetime.combine(end, time.max, IST) if end else None
    return lo, hi


def default_range(start: date | None, end: date | None, days: int = 30) -> tuple[date, date]:
    end = end or today_ist()
    return start or end - timedelta(days=days - 1), end


def in_ist(ts: datetime) -> datetime:
    return ts.astimezone(IST)


def collector_code(collector_id: int) -> str:
    return f"MITRA-C-{collector_id:06d}"


def collector_out(c: Collector) -> CollectorOut:
    return CollectorOut(id=c.id, code=collector_code(c.id), name=c.name, area=c.area,
                        phone=c.phone, registered_ts=in_ist(c.registered_ts))


def price_at(t: Transaction, m: Material) -> float:
    """Price shown when the lot was logged (current price only for rows from before the upgrade)."""
    return t.ref_price_per_kg if t.ref_price_per_kg is not None else m.ref_price_per_kg


def material_out(m: Material, latest: dict) -> MaterialOut:
    """Material with when and where its current price came from."""
    u = latest.get(m.id)
    return MaterialOut(**m.model_dump(), price_updated_at=in_ist(u.ts) if u else None,
                       price_source=u.source if u else None)


def transaction_outs(session: Session, txs: list[Transaction]) -> list[TransactionOut]:
    if not txs:
        return []
    ids = [t.id for t in txs]
    materials = {m.id: m for m in session.exec(select(Material))}
    names = {c.id: c.name for c in session.exec(
        select(Collector).where(Collector.id.in_({t.collector_id for t in txs})))}
    statuses = {p.transaction_id: p.status for p in session.exec(
        select(MaterialPassport).where(MaterialPassport.transaction_id.in_(ids)))}
    out = []
    for t in txs:
        m = materials[t.material_id]
        out.append(TransactionOut(
            id=t.id, collector_id=t.collector_id, collector_name=names[t.collector_id],
            material_id=m.id, material=m.name, category=m.category,
            weight_kg=t.weight_kg, amount_paid=t.amount_paid,
            ref_price_per_kg=price_at(t, m), ref_amount=quote(price_at(t, m), t.weight_kg),
            gps_lat=t.gps_lat, gps_lon=t.gps_lon, photo_url=t.photo_url,
            cv_suggested=t.cv_suggested, cv_confidence=t.cv_confidence,
            ts=in_ist(t.ts), aggregator_id=t.aggregator_id,
            passport_id=passport_id(t.id), passport_status=statuses.get(t.id, "collected"),
        ))
    return out
