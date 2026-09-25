import pytest

from app.engine.pricing import UnknownMaterial, load_prices, parse_prices, quote, ref_price

ROWS = [
    {"material": "PET plastic", "category": "pet", "ref_price_per_kg": "12"},
    {"material": "Copper", "category": "metal", "ref_price_per_kg": "400"},
]


def test_parse_and_lookup():
    prices = parse_prices(ROWS)
    assert prices["Copper"].category == "metal"
    assert ref_price(prices, "PET plastic") == 12.0
    assert ref_price(prices, "  copper ") == 400.0  # case/space tolerant


def test_unknown_material_raises():
    with pytest.raises(UnknownMaterial):
        ref_price(parse_prices(ROWS), "Unobtainium")


def test_rejects_bad_rows():
    with pytest.raises(ValueError):
        parse_prices([{"material": "Glass", "category": "glass", "ref_price_per_kg": "0"}])
    with pytest.raises(ValueError):
        parse_prices(ROWS + ROWS[:1])


def test_quote():
    assert quote(400, 2.5) == 1000.0
    assert quote(12, 3.33) == 39.96
    with pytest.raises(ValueError):
        quote(12, 0)


def test_shipped_price_file_has_six_categories():
    prices = load_prices()
    assert {p.category for p in prices.values()} == {"pet", "hdpe", "paper", "glass", "metal", "ewaste"}
    assert ref_price(prices, "Copper") == 400
