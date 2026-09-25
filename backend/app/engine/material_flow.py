"""Sankey source data: kg flowing collector -> aggregator -> recycler, by material.

Material without a material passport has no verified recycler yet; it flows
into an explicit "Awaiting dispatch" node instead of an invented destination.
"""
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

AWAITING = "Awaiting dispatch"
STAGE_ORDER = {"collector": 0, "aggregator": 1, "recycler": 2, "pending": 3}


@dataclass(frozen=True)
class FlowRecord:
    collector: str  # node label: a collector or a collector group (e.g. area)
    aggregator: str
    recycler: str | None  # None = no verified downstream custody yet
    material: str  # category: pet | hdpe | paper | glass | metal | ewaste
    kg: float
    material_name: str = ""  # e.g. "Copper" within category "metal"


def kg_by_material(records: Iterable[FlowRecord], by: Literal["category", "name"] = "category") -> dict[str, float]:
    """Total kg per material category (or per material name), largest first."""
    totals: dict[str, float] = defaultdict(float)
    for r in records:
        totals[r.material_name if by == "name" else r.material] += r.kg
    return {m: round(kg, 1) for m, kg in sorted(totals.items(), key=lambda kv: -kv[1])}


def traced_share(records: Iterable[FlowRecord]) -> dict[str, float]:
    """How much of the collected kg has a verified chain to a recycler."""
    total = traced = 0.0
    for r in records:
        total += r.kg
        if r.recycler is not None:
            traced += r.kg
    pct = round(100 * traced / total, 1) if total else 0.0
    return {"kg_total": round(total, 1), "kg_traced": round(traced, 1), "pct_traced": pct}


def build_sankey(records: Iterable[FlowRecord]) -> dict[str, list[dict]]:
    """Nodes + links for a Sankey. Links reference node indices; `value` is kg.

    One link per (source, target, material) so the frontend can colour by material.
    """
    weights: dict[tuple[tuple[str, str], tuple[str, str], str], float] = defaultdict(float)
    for r in records:
        c, a = ("collector", r.collector), ("aggregator", r.aggregator)
        d = ("recycler", r.recycler) if r.recycler is not None else ("pending", AWAITING)
        weights[(c, a, r.material)] += r.kg
        weights[(a, d, r.material)] += r.kg

    keys = sorted({k for src, dst, _ in weights for k in (src, dst)},
                  key=lambda k: (STAGE_ORDER[k[0]], k[1]))
    index = {k: i for i, k in enumerate(keys)}
    links = sorted(
        ({"source": index[src], "target": index[dst], "material": mat, "value": round(kg, 1)}
         for (src, dst, mat), kg in weights.items()),
        key=lambda link: (link["source"], link["target"], link["material"]),
    )
    return {"nodes": [{"name": name, "stage": stage} for stage, name in keys], "links": links}
