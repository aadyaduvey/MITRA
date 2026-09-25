"""EPR compliance report data: what was collected in a period, and how much of it
reached a CPCB-authorised recycler with a verified chain of custody.

Only `delivered` lots count as recycled for EPR; `in_transit` lots are shown
separately; lots without a passport are collected-but-untraced.
"""
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class EprLot:
    passport_id: str
    transaction_id: int
    collector_id: int
    collected_at: str  # ISO, IST
    material: str
    category: str
    kg: float
    aggregator: str | None
    recycler: str | None
    recycler_cpcb_reg_no: str | None
    status: str  # collected | in_transit | delivered
    delivered_at: str | None  # ISO, IST


def _material_rows(lots: list[EprLot]) -> list[dict]:
    rows: dict[str, dict] = {}
    for lot in lots:
        row = rows.setdefault(lot.material, {
            "material": lot.material, "category": lot.category, "lots": 0,
            "kg_collected": 0.0, "kg_in_transit": 0.0, "kg_delivered": 0.0,
        })
        row["lots"] += 1
        row["kg_collected"] += lot.kg
        if lot.status in ("delivered", "in_transit"):
            row[f"kg_{lot.status}"] += lot.kg
    return sorted((_round(r) for r in rows.values()), key=lambda r: -r["kg_collected"])


def _recycler_rows(lots: list[EprLot]) -> list[dict]:
    rows: dict[str, dict] = {}
    for lot in lots:
        if lot.recycler is None:
            continue
        row = rows.setdefault(lot.recycler_cpcb_reg_no or lot.recycler, {
            "name": lot.recycler, "cpcb_reg_no": lot.recycler_cpcb_reg_no, "lots": 0,
            "kg_in_transit": 0.0, "kg_delivered": 0.0, "kg_by_material": defaultdict(float),
        })
        row["lots"] += 1
        row[f"kg_{lot.status}"] += lot.kg
        row["kg_by_material"][lot.material] += lot.kg
    out = []
    for row in rows.values():
        row["kg_by_material"] = {m: round(kg, 1) for m, kg in sorted(row["kg_by_material"].items())}
        out.append(_round(row))
    return sorted(out, key=lambda r: r["name"])


def _round(row: dict) -> dict:
    return {k: round(v, 1) if isinstance(v, float) else v for k, v in row.items()}


def build_epr_report(lots: Iterable[EprLot], start: date, end: date, generated_at: datetime) -> dict:
    lots = sorted(lots, key=lambda lot: (lot.collected_at, lot.transaction_id))
    kg = lambda status: round(sum(lot.kg for lot in lots if lot.status == status), 1)  # noqa: E731
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "generated_at": generated_at.isoformat(),
        "totals": {
            "lots": len(lots),
            "collectors": len({lot.collector_id for lot in lots}),
            "kg_collected": round(sum(lot.kg for lot in lots), 1),
            "kg_in_transit": kg("in_transit"),
            "kg_delivered": kg("delivered"),
        },
        "by_material": _material_rows(lots),
        "recyclers": _recycler_rows(lots),
        "collector_ids": sorted({lot.collector_id for lot in lots}),
        "lots": [asdict(lot) for lot in lots if lot.recycler is not None],
    }
