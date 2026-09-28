"""Reference prices: list, set by hand, fetch live metal prices, history."""
import logging

from fastapi import APIRouter, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlmodel import Session, select

from app.api.deps import SessionDep, in_ist, material_out
from app.models import Material
from app.prices import live
from app.prices.service import PriceError, ensure_price_history, history, latest_updates, set_price
from app.schemas import LiveRefresh, PriceBoard, PriceHistoryRow, PriceRow, PriceSet

router = APIRouter(prefix="/api/prices", tags=["prices"])
log = logging.getLogger("mitra.prices")


def _row(m: Material, latest: dict) -> PriceRow:
    rule = live.LIVE_RULES.get(m.name)
    return PriceRow(**material_out(m, latest).model_dump(), live=rule is not None,
                    live_rule=rule.describe() if rule else None)


@router.get("", response_model=PriceBoard)
def price_board(session: SessionDep) -> PriceBoard:
    latest = latest_updates(session)
    rows = [_row(m, latest) for m in session.exec(select(Material).order_by(Material.id))]
    return PriceBoard(live_configured=live.api_key() is not None, live_provider=live.PROVIDER, prices=rows)


@router.put("/{material_id}", response_model=PriceRow)
def update_price(material_id: int, body: PriceSet, session: SessionDep) -> PriceRow:
    m = session.get(Material, material_id)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"material {material_id} not found")
    try:
        set_price(session, m, body.ref_price_per_kg, body.source)
    except PriceError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    return _row(m, latest_updates(session))


@router.post("/live", response_model=LiveRefresh)
async def refresh_live_prices(session: SessionDep) -> LiveRefresh:
    return LiveRefresh(**await run_in_threadpool(live.refresh_live, session))


@router.get("/history", response_model=list[PriceHistoryRow])
def price_history(session: SessionDep, material_id: int | None = None,
                  limit: int = 100) -> list[PriceHistoryRow]:
    names = {m.id: m.name for m in session.exec(select(Material))}
    return [PriceHistoryRow(id=u.id, material_id=u.material_id, material=names.get(u.material_id, "?"),
                            price_per_kg=u.price_per_kg, previous_price=u.previous_price,
                            source=u.source, ts=in_ist(u.ts))
            for u in history(session, material_id, min(max(limit, 1), 500))]


def refresh_on_startup(bind) -> None:
    """Background thread at API start: live refresh if a key is set and prices are stale.
    A price-feed problem is logged and never stops the API."""
    try:
        with Session(bind) as session:
            ensure_price_history(session)
            out = live.refresh_if_stale(session)
        for r in (out or {}).get("results", []):
            log.info("Live price %s: %s (%s)", r["material"], r["status"], r["detail"])
    except Exception:
        log.exception("Live price refresh failed; manual prices stay in use")
