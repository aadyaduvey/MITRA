"""Collectors: register (chat signup) and look up."""
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from sqlmodel import func, select

from app.api.deps import SessionDep, collector_code, collector_out, in_ist, transaction_outs
from app.engine.loaders import stored_photo_path
from app.models import IST, Collector, Transaction
from app.schemas import CollectorCreate, CollectorDetail, CollectorErased, CollectorOut, CollectorSummary

router = APIRouter(prefix="/api/collectors", tags=["collectors"])

ERASED_NAME = "Erased collector"


@router.post("", response_model=CollectorOut, status_code=status.HTTP_201_CREATED)
def register_collector(body: CollectorCreate, session: SessionDep) -> CollectorOut:
    if body.phone and session.exec(select(Collector).where(Collector.phone == body.phone)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "a collector with this phone is already registered")
    c = Collector(**body.model_dump(), registered_ts=datetime.now(IST).replace(microsecond=0))
    session.add(c)
    session.commit()
    session.refresh(c)
    return collector_out(c)


def _summary(c: Collector, stats: dict, last: Transaction | None) -> dict:
    lots, kg = stats.get(c.id, (0, 0.0))
    return {
        **collector_out(c).model_dump(),
        "lots": lots,
        "kg": round(kg or 0.0, 1),
        "last_ts": in_ist(last.ts) if last else None,
        "last_lat": last.gps_lat if last else None,
        "last_lon": last.gps_lon if last else None,
    }


@router.get("", response_model=list[CollectorSummary])
def list_collectors(session: SessionDep) -> list[CollectorSummary]:
    stats = {cid: (n, kg) for cid, n, kg in session.exec(
        select(Transaction.collector_id, func.count(), func.sum(Transaction.weight_kg))
        .group_by(Transaction.collector_id))}
    last: dict[int, Transaction] = {}
    for t in session.exec(select(Transaction).order_by(Transaction.ts)):
        last[t.collector_id] = t  # ends on each collector's latest
    collectors = session.exec(select(Collector).order_by(Collector.id)).all()
    return [CollectorSummary(**_summary(c, stats, last.get(c.id))) for c in collectors]


@router.get("/{collector_id}", response_model=CollectorDetail)
def get_collector(collector_id: int, session: SessionDep, limit: int = 10) -> CollectorDetail:
    c = session.get(Collector, collector_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"collector {collector_id} not found")
    q = select(Transaction).where(Transaction.collector_id == c.id)
    recent = list(session.exec(q.order_by(Transaction.ts.desc(), Transaction.id.desc()).limit(limit)))
    n, kg = session.exec(
        select(func.count(), func.sum(Transaction.weight_kg)).where(Transaction.collector_id == c.id)
    ).one()
    return CollectorDetail(
        **_summary(c, {c.id: (n, kg)}, recent[0] if recent else None),
        recent_transactions=transaction_outs(session, recent),
    )


@router.delete("/{collector_id}", response_model=CollectorErased)
def erase_collector(collector_id: int, session: SessionDep) -> CollectorErased:
    """Right to erasure (DPDP Act): delete the collector's personal data and photos.

    Their lots stay, anonymous, because filed EPR reports and custody chains depend
    on them. The area (a locality, not an address) is kept for geography totals.
    """
    c = session.get(Collector, collector_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"collector {collector_id} not found")
    txs = session.exec(select(Transaction).where(Transaction.collector_id == c.id)).all()
    photos = 0
    for t in txs:
        path = stored_photo_path(t.photo_url)
        if path is not None:
            path.unlink(missing_ok=True)
            photos += 1
        if t.photo_url:
            t.photo_url = None
            session.add(t)
    c.name, c.phone, c.aadhaar_last4 = ERASED_NAME, None, None
    session.add(c)
    session.commit()
    return CollectorErased(id=c.id, code=collector_code(c.id), lots_kept=len(txs), photos_deleted=photos)
