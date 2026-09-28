"""Commodity reference prices (INR/kg) and payout quotes.

Reference price = wholesale/market price minus fair intermediary margin, per kg.
Defaults live in backend/data/commodity_prices.csv (material, category,
ref_price_per_kg, source, updated_on). Prices are changed with
`uv run python -m app.prices set ...`, the dashboard Prices page, or the live metal
feed (app/prices/live.py); each change is saved to the database and to this file.
"""
import csv
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

PRICES_CSV = Path(__file__).resolve().parents[2] / "data" / "commodity_prices.csv"
CSV_FIELDS = ["material", "category", "ref_price_per_kg", "source", "updated_on"]


@dataclass(frozen=True)
class Price:
    material: str
    category: str
    ref_price_per_kg: float
    source: str = ""
    updated_on: str = ""  # ISO date, "" if unknown


class UnknownMaterial(KeyError):
    pass


def parse_prices(rows: Iterable[Mapping[str, str]]) -> dict[str, Price]:
    """CSV rows -> {material: Price}. `source` and `updated_on` columns are optional."""
    prices: dict[str, Price] = {}
    for row in rows:
        name = row["material"].strip()
        value = float(row["ref_price_per_kg"])
        if value <= 0:
            raise ValueError(f"non-positive price for {name!r}: {value}")
        if name in prices:
            raise ValueError(f"duplicate material {name!r}")
        prices[name] = Price(name, row["category"].strip(), value,
                             (row.get("source") or "").strip(), (row.get("updated_on") or "").strip())
    return prices


def load_prices(path: Path | None = None) -> dict[str, Price]:
    with (path or PRICES_CSV).open(newline="", encoding="utf-8") as f:
        return parse_prices(csv.DictReader(f))


def save_price(material: str, price: float, source: str, updated_on: str, path: Path | None = None) -> None:
    """Rewrite one material's row in the price file (other rows unchanged)."""
    path = path or PRICES_CSV
    prices = load_prices(path)
    if material not in prices:
        raise UnknownMaterial(material)
    old = prices[material]
    prices[material] = Price(material, old.category, price, source, updated_on)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for p in prices.values():
            writer.writerow({"material": p.material, "category": p.category,
                             "ref_price_per_kg": f"{p.ref_price_per_kg:g}",
                             "source": p.source, "updated_on": p.updated_on})


def ref_price(prices: Mapping[str, Price], material: str) -> float:
    """Reference price per kg; lookup ignores case and surrounding spaces."""
    key = material.strip().casefold()
    for name, price in prices.items():
        if name.casefold() == key:
            return price.ref_price_per_kg
    raise UnknownMaterial(material)


def quote(ref_price_per_kg: float, weight_kg: float) -> float:
    """Amount (INR) a collector should receive for `weight_kg` at reference price."""
    if weight_kg <= 0:
        raise ValueError(f"weight must be positive, got {weight_kg}")
    return round(ref_price_per_kg * weight_kg, 2)
