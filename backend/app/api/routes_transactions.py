"""Materials (for pickers) and transactions (log a lot, list lots for the map)."""
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlmodel import select

from app.api.deps import SessionDep, day_bounds, transaction_outs
from app.engine.pricing import quote
from app.models import IST, Aggregator, Collector, Material, Transaction
from app.schemas import MaterialOut, TransactionCreate, TransactionOut

router = APIRouter(prefix="/api", tags=["transactions"])


@router.get("/materials", response_model=list[MaterialOut])
def list_materials(session: SessionDep) -> list[MaterialOut]:
    return [MaterialOut(**m.model_dump()) for m in session.exec(select(Material).order_by(Material.id))]


def _unprocessable(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, msg)


@router.post("/transactions", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def log_transaction(body: TransactionCreate, session: SessionDep) -> TransactionOut:
    if session.get(Collector, body.collector_id) is None:
        raise _unprocessable(f"unknown collector_id {body.collector_id}")
    material = session.get(Material, body.material_id)
    if material is None:
        raise _unprocessable(f"unknown material_id {body.material_id}")
    if body.aggregator_id is not None and session.get(Aggregator, body.aggregator_id) is None:
        raise _unprocessable(f"unknown aggregator_id {body.aggregator_id}")

    ts = body.ts or datetime.now(IST)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=IST)
    amount = body.amount_paid if body.amount_paid is not None else quote(
        material.ref_price_per_kg, body.weight_kg)
    tx = Transaction(**body.model_dump(exclude={"ts", "amount_paid"}),
                     amount_paid=round(amount, 2), ts=ts.replace(microsecond=0))
    session.add(tx)
    session.commit()
    session.refresh(tx)
    return transaction_outs(session, [tx])[0]


@router.get("/transactions", response_model=list[TransactionOut])
def list_transactions(
    session: SessionDep,
    collector_id: int | None = None,
    start: date | None = Query(None, description="IST day, inclusive"),
    end: date | None = Query(None, description="IST day, inclusive"),
    limit: int = Query(1000, ge=1, le=5000),
) -> list[TransactionOut]:
    q = select(Transaction)
    if collector_id is not None:
        q = q.where(Transaction.collector_id == collector_id)
    lo, hi = day_bounds(start, end)
    if lo is not None:
        q = q.where(Transaction.ts >= lo)
    if hi is not None:
        q = q.where(Transaction.ts <= hi)
    txs = list(session.exec(q.order_by(Transaction.ts.desc(), Transaction.id.desc()).limit(limit)))
    return transaction_outs(session, txs)
