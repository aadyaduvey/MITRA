"""EPR compliance PDF (reportlab). Input is the EprReport dict; output is PDF bytes."""
import io
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

NAVY = colors.HexColor("#0B2A4A")
RULE = colors.HexColor("#C8D1DC")
ZEBRA = colors.HexColor("#F3F6F9")
MARGIN = 14 * mm
FOOTER = "MITRA proof of concept. Not an official CPCB filing."

_styles = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=_styles["Title"], fontSize=16, textColor=colors.white,
                    alignment=0, spaceAfter=0, leading=20)
SUB = ParagraphStyle("sub", parent=_styles["Normal"], fontSize=9, textColor=colors.white)
H2 = ParagraphStyle("h2", parent=_styles["Heading2"], fontSize=11, textColor=NAVY,
                    spaceBefore=8, spaceAfter=4)
BODY = ParagraphStyle("body", parent=_styles["Normal"], fontSize=8.5, leading=11)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=7.5, leading=9)
CELL_R = ParagraphStyle("cellr", parent=CELL, alignment=TA_RIGHT)


def _kg(v: float) -> str:
    return f"{v:,.1f}"


def _day(iso: str | None, fmt: str = "%d %b %Y") -> str:
    return datetime.fromisoformat(iso).strftime(fmt) if iso else "-"


def _table(header: list[str], rows: list[list], widths: list[float], numeric: set[int],
           empty: str) -> Table:
    if not rows:
        rows = [[empty] + [""] * (len(header) - 1)]
    body = [[Paragraph(escape(str(v)), CELL_R if i in numeric else CELL) for i, v in enumerate(r)]
            for r in rows]
    head = [Paragraph(f"<b>{escape(h)}</b>", CELL_R if i in numeric else CELL)
            for i, h in enumerate(header)]
    t = Table([head] + body, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDE5EE")),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ZEBRA]),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _banner(report: dict, width: float) -> Table:
    p = report["period"]
    t = Table([[Paragraph("EPR Compliance Report: First-Mile Material Recovery", H1)],
               [Paragraph(f"Period {_day(p['start'])} to {_day(p['end'])}  |  Generated "
                          f"{datetime.fromisoformat(report['generated_at']):%d %b %Y %H:%M} IST  |  "
                          "Source: MITRA collector transactions and material passports", SUB)]],
              colWidths=[width])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, 0), 8),
                           ("BOTTOMPADDING", (0, -1), (-1, -1), 8)]))
    return t


def _kpis(totals: dict, width: float) -> Table:
    cells = [("Lots logged", f"{totals['lots']:,}"),
             ("Collectors", f"{totals['collectors']:,}"),
             ("kg collected", _kg(totals["kg_collected"])),
             ("kg delivered to authorised recyclers", _kg(totals["kg_delivered"])),
             ("kg in transit", _kg(totals["kg_in_transit"]))]
    big = ParagraphStyle("big", parent=BODY, fontSize=13, leading=16, textColor=NAVY)
    t = Table([[Paragraph(f"<b>{v}</b>", big) for _, v in cells],
               [Paragraph(escape(k), CELL) for k, _ in cells]],
              colWidths=[width / len(cells)] * len(cells))
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, RULE),
                           ("LINEAFTER", (0, 0), (-2, -1), 0.5, RULE),
                           ("TOPPADDING", (0, 0), (-1, -1), 4),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return t


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.grey)
    canvas.drawString(MARGIN, 8 * mm, FOOTER)
    canvas.drawRightString(A4[0] - MARGIN, 8 * mm, f"Page {doc.page}")
    canvas.restoreState()


def render_epr_pdf(report: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=MARGIN, bottomMargin=14 * mm,
                            title="MITRA EPR Compliance Report", author="MITRA")
    w = A4[0] - 2 * MARGIN
    story = [_banner(report, w), Spacer(1, 6), _kpis(report["totals"], w)]

    story += [Paragraph("1. Material collected and recovered", H2), _table(
        ["Material", "Category", "Lots", "kg collected", "kg in transit", "kg delivered"],
        [[r["material"], r["category"], r["lots"], _kg(r["kg_collected"]),
          _kg(r["kg_in_transit"]), _kg(r["kg_delivered"])] for r in report["by_material"]],
        [w * f for f in (0.34, 0.12, 0.09, 0.15, 0.15, 0.15)], {2, 3, 4, 5},
        "No lots in this period")]

    story += [Paragraph("2. Destination recyclers (CPCB-authorised)", H2), _table(
        ["Recycler", "CPCB registration no.", "Lots", "kg delivered", "kg in transit"],
        [[r["name"], r["cpcb_reg_no"] or "-", r["lots"], _kg(r["kg_delivered"]),
          _kg(r["kg_in_transit"])] for r in report["recyclers"]],
        [w * f for f in (0.38, 0.30, 0.08, 0.12, 0.12)], {2, 3, 4},
        "No material reached a recycler in this period")]

    story += [Paragraph("3. Lot-level chain of custody", H2), _table(
        ["Passport", "Collector", "Collected", "Material", "kg", "Recycler CPCB reg. no.",
         "Status", "Delivered"],
        [[lot["passport_id"], f"C-{lot['collector_id']:06d}", _day(lot["collected_at"], "%d %b"),
          lot["material"], _kg(lot["kg"]), lot["recycler_cpcb_reg_no"] or "-",
          lot["status"].replace("_", " "), _day(lot["delivered_at"], "%d %b")] for lot in report["lots"]],
        [w * f for f in (0.14, 0.095, 0.08, 0.235, 0.06, 0.225, 0.085, 0.08)], {4},
        "No traced lots in this period")]

    ids = ", ".join(f"C-{i:06d}" for i in report["collector_ids"]) or "none"
    story += [Paragraph("4. Contributing collectors", H2),
              Paragraph(f"{len(report['collector_ids'])} collector IDs: {ids}", CELL),
              Spacer(1, 6),
              Paragraph("Delivered = recycler receipt recorded in the material passport. "
                        "In transit = dispatched by aggregator, receipt pending. Lots without a "
                        "passport are counted as collected only. Weights are as logged by the "
                        "collector at the point of collection.", CELL)]
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
