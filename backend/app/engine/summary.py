"""Ministry overview: national-scale view of first-mile material, led by metals.

Values are at reference price (see pricing.py), not realised sale prices.
"""
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

METAL_BEARING = ("metal", "ewaste")  # e-waste counted as a metal-bearing stream


@dataclass(frozen=True)
class Lot:
    collector_id: int
    area: str
    material: str
    category: str
    kg: float
    ref_price_per_kg: float
    amount_paid: float
    lat: float | None
    lon: float | None
    traced: bool  # has a verified chain to a recycler


def _by(lots: list[Lot], key) -> dict[str, list[Lot]]:
    groups: dict[str, list[Lot]] = defaultdict(list)
    for lot in lots:
        groups[key(lot)].append(lot)
    return groups


def _kg(lots: Iterable[Lot]) -> float:
    return round(sum(lot.kg for lot in lots), 1)


def _value(lots: Iterable[Lot]) -> float:
    return round(sum(lot.kg * lot.ref_price_per_kg for lot in lots), 0)


def _area_row(area: str, lots: list[Lot]) -> dict:
    located = [lot for lot in lots if lot.lat is not None and lot.lon is not None]
    return {
        "area": area,
        "kg": _kg(lots),
        "lots": len(lots),
        "collectors": len({lot.collector_id for lot in lots}),
        "lat": round(sum(lot.lat for lot in located) / len(located), 5) if located else None,
        "lon": round(sum(lot.lon for lot in located) / len(located), 5) if located else None,
    }


def ministry_summary(lots: Iterable[Lot], registered_collectors: int) -> dict:
    lots = list(lots)
    total_value = _value(lots)
    metal = [lot for lot in lots if lot.category in METAL_BEARING]
    metal_value = _value(metal)
    kg_total = _kg(lots)
    kg_traced = _kg(lot for lot in lots if lot.traced)
    return {
        "totals": {
            "kg": kg_total,
            "lots": len(lots),
            "value_at_ref_inr": total_value,
            "amount_paid_inr": round(sum(lot.amount_paid for lot in lots), 0),
            "active_collectors": len({lot.collector_id for lot in lots}),
            "registered_collectors": registered_collectors,
            "kg_traced": kg_traced,
            "pct_traced": round(100 * kg_traced / kg_total, 1) if kg_total else 0.0,
        },
        "by_material": sorted(
            ({"material": m, "category": g[0].category, "kg": _kg(g), "lots": len(g),
              "value_at_ref_inr": _value(g)} for m, g in _by(lots, lambda lot: lot.material).items()),
            key=lambda r: -r["kg"],
        ),
        "by_category": dict(sorted(
            ((c, _kg(g)) for c, g in _by(lots, lambda lot: lot.category).items()),
            key=lambda kv: -kv[1],
        )),
        "by_area": sorted(
            (_area_row(a, g) for a, g in _by(lots, lambda lot: lot.area).items()),
            key=lambda r: -r["kg"],
        ),
        "metal_recovery": {
            "kg": _kg(metal),
            "value_at_ref_inr": metal_value,
            "pct_of_total_value": round(100 * metal_value / total_value, 1) if total_value else 0.0,
            "materials": sorted(
                ({"material": m, "kg": _kg(g), "value_at_ref_inr": _value(g)}
                 for m, g in _by(metal, lambda lot: lot.material).items()),
                key=lambda r: -r["value_at_ref_inr"],
            ),
        },
    }
