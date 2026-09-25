"""Ministry overview and material-flow (Sankey) data."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Query

from app.api.deps import SessionDep, day_bounds
from app.engine.loaders import collector_count, flow_records, summary_lots
from app.engine.material_flow import build_sankey, traced_share
from app.engine.summary import ministry_summary
from app.schemas import MinistrySummary, Period, Sankey

router = APIRouter(prefix="/api", tags=["ministry"])

StartQ = Query(None, description="IST day, inclusive (omit both for all data)")
EndQ = Query(None, description="IST day, inclusive")


def _bounds(start: date | None, end: date | None):
    if start is None and end is None:
        return None, None, None
    lo, hi = day_bounds(start, end)
    return lo, hi, Period(start=start.isoformat() if start else "", end=end.isoformat() if end else "")


@router.get("/ministry/summary", response_model=MinistrySummary)
def summary(session: SessionDep, start: date | None = StartQ,
            end: date | None = EndQ) -> MinistrySummary:
    lo, hi, period = _bounds(start, end)
    data = ministry_summary(summary_lots(session, lo, hi), collector_count(session))
    return MinistrySummary(period=period, **data)


@router.get("/flow/sankey", response_model=Sankey)
def sankey(session: SessionDep, group_by: Literal["area", "collector"] = "area",
           start: date | None = StartQ, end: date | None = EndQ) -> Sankey:
    lo, hi, _ = _bounds(start, end)
    records = flow_records(session, group_by=group_by, start=lo, end=hi)
    return Sankey(**build_sankey(records), **traced_share(records))
