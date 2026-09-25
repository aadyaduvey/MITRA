"""Commodity reference prices (INR/kg) and payout quotes.

Reference price = wholesale/MCX spot minus intermediary margins, per kg.
Values come from backend/data/commodity_prices.csv (indicative FY24-25).
"""
import csv
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

PRICES_CSV = Path(__file__).resolve().parents[2] / "data" / "commodity_prices.csv"


@dataclass(frozen=True)
class Price:
    material: str
    category: str
    ref_price_per_kg: float


class UnknownMaterial(KeyError):
    pass


def parse_prices(rows: Iterable[Mapping[str, str]]) -> dict[str, Price]:
    """CSV rows (material, category, ref_price_per_kg) -> {material: Price}."""
    prices: dict[str, Price] = {}
    for row in rows:
        name = row["material"].strip()
        value = float(row["ref_price_per_kg"])
        if value <= 0:
            raise ValueError(f"non-positive price for {name!r}: {value}")
        if name in prices:
            raise ValueError(f"duplicate material {name!r}")
        prices[name] = Price(name, row["category"].strip(), value)
    return prices


def load_prices(path: Path = PRICES_CSV) -> dict[str, Price]:
    with path.open(newline="", encoding="utf-8") as f:
        return parse_prices(csv.DictReader(f))


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
