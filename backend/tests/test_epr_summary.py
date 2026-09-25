from datetime import date, datetime

from app.engine.epr import EprLot, build_epr_report
from app.engine.summary import Lot, ministry_summary
from app.reports.epr_pdf import render_epr_pdf


def lot(tx, status, kg, material="Copper", recycler="Rec & Co", reg="CPCB-9", collector=1):
    traced = status != "collected"
    return EprLot(
        passport_id=f"MITRA-P-{tx:06d}", transaction_id=tx, collector_id=collector,
        collected_at=f"2026-09-{10 + tx:02d}T10:00:00+05:30", material=material, category="metal",
        kg=kg, aggregator="Agg", recycler=recycler if traced else None,
        recycler_cpcb_reg_no=reg if traced else None, status=status,
        delivered_at="2026-09-20T10:00:00+05:30" if status == "delivered" else None,
    )


LOTS = [lot(1, "delivered", 4.0), lot(2, "in_transit", 1.5), lot(3, "collected", 10.0, collector=2),
        lot(4, "delivered", 6.0, material="Metal (blend)")]
GEN = datetime(2026, 9, 26, 12, 0)


def test_epr_totals_and_eligibility():
    r = build_epr_report(LOTS, date(2026, 9, 1), date(2026, 9, 30), GEN)
    assert r["totals"] == {"lots": 4, "collectors": 2, "kg_collected": 21.5,
                           "kg_in_transit": 1.5, "kg_delivered": 10.0}
    assert [l["transaction_id"] for l in r["lots"]] == [1, 2, 4]  # untraced lot excluded
    assert r["collector_ids"] == [1, 2]


def test_epr_per_material_and_recycler():
    r = build_epr_report(LOTS, date(2026, 9, 1), date(2026, 9, 30), GEN)
    copper = next(m for m in r["by_material"] if m["material"] == "Copper")
    assert copper == {"material": "Copper", "category": "metal", "lots": 3, "kg_collected": 15.5,
                      "kg_in_transit": 1.5, "kg_delivered": 4.0}
    [rec] = r["recyclers"]
    assert rec["cpcb_reg_no"] == "CPCB-9" and rec["kg_delivered"] == 10.0 and rec["lots"] == 3
    assert rec["kg_by_material"] == {"Copper": 5.5, "Metal (blend)": 6.0}


def test_epr_empty_period():
    r = build_epr_report([], date(2026, 1, 1), date(2026, 1, 2), GEN)
    assert r["totals"]["lots"] == 0 and r["lots"] == [] and r["recyclers"] == []


def test_pdf_renders_including_empty_and_markup_chars():
    for lots in (LOTS, []):
        pdf = render_epr_pdf(build_epr_report(lots, date(2026, 9, 1), date(2026, 9, 30), GEN))
        assert pdf.startswith(b"%PDF") and len(pdf) > 1500


def slot(cid, area, material, category, kg, price, lat=26.9, lon=75.8, traced=False):
    return Lot(cid, area, material, category, kg, price, kg * price * 0.9, lat, lon, traced)


def test_ministry_summary():
    lots = [slot(1, "A", "Copper", "metal", 2.0, 400, traced=True),
            slot(1, "A", "Glass", "glass", 20.0, 2),
            slot(2, "B", "E-waste", "ewaste", 4.0, 25, lat=None, lon=None)]
    s = ministry_summary(lots, registered_collectors=5)
    t = s["totals"]
    assert (t["kg"], t["lots"], t["active_collectors"], t["registered_collectors"]) == (26.0, 3, 2, 5)
    assert t["value_at_ref_inr"] == 800 + 40 + 100
    assert t["kg_traced"] == 2.0 and t["pct_traced"] == 7.7
    m = s["metal_recovery"]
    assert m["kg"] == 6.0 and m["value_at_ref_inr"] == 900
    assert [r["material"] for r in m["materials"]] == ["Copper", "E-waste"]
    area_b = next(a for a in s["by_area"] if a["area"] == "B")
    assert area_b["lat"] is None  # no GPS -> no centroid, no crash
    assert s["by_category"] == {"glass": 20.0, "ewaste": 4.0, "metal": 2.0}


def test_ministry_summary_empty():
    s = ministry_summary([], registered_collectors=0)
    assert s["totals"]["kg"] == 0 and s["totals"]["pct_traced"] == 0.0
    assert s["metal_recovery"]["pct_of_total_value"] == 0.0
