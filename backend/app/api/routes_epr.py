"""EPR compliance report for a date range, as JSON, PDF or CSV."""
import csv
import io
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Query, Response

from app.api.deps import SessionDep, day_bounds, default_range
from app.engine.epr import build_epr_report
from app.engine.loaders import epr_lots
from app.models import IST
from app.reports.epr_pdf import render_epr_pdf
from app.schemas import EprLotOut, EprReport

router = APIRouter(prefix="/api/epr", tags=["epr"])


def _csv(report: EprReport) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(EprLotOut.model_fields))
    writer.writeheader()
    for lot in report.lots:
        writer.writerow(lot.model_dump())
    return buf.getvalue()


@router.get(
    "/report",
    response_model=EprReport,
    responses={200: {"content": {"application/pdf": {}, "text/csv": {}}}},
)
def epr_report(
    session: SessionDep,
    start: date | None = Query(None, description="IST day, inclusive (default: 30 days before end)"),
    end: date | None = Query(None, description="IST day, inclusive (default: today)"),
    format: Literal["json", "pdf", "csv"] = "json",
):
    start, end = default_range(start, end)
    lo, hi = day_bounds(start, end)
    generated = datetime.now(IST).replace(microsecond=0)
    report = EprReport(**build_epr_report(epr_lots(session, lo, hi), start, end, generated))
    stem = f"mitra-epr-{start.isoformat()}-to-{end.isoformat()}"
    if format == "pdf":
        return Response(render_epr_pdf(report.model_dump()), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{stem}.pdf"'})
    if format == "csv":
        return Response(_csv(report), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{stem}.csv"'})
    return report
