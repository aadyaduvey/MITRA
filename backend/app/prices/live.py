"""Live metal prices from MetalpriceAPI (https://metalpriceapi.com, free key).

Reference price for a collector = market metal price (INR/kg)
                                  x scrap share (mixed scrap trades below pure metal)
                                  x (1 - fair trader margin)
Only metals with a market feed are live. Steel scrap, paper, PET, glass and
e-waste have no free feed and are set by hand. On any failure the last saved
price is kept, and a result outside a believable range is rejected, not saved.

Set the key in backend/.env:  METAL_PRICE_API_KEY=your-key
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx
from sqlmodel import Session, select

from app.config import env_value
from app.models import IST, Material, PriceUpdate
from app.prices.service import set_price

PROVIDER = "MetalpriceAPI"
PROVIDER_URL = "https://api.metalpriceapi.com/v1/latest"
KEY_NAME = "METAL_PRICE_API_KEY"
OZ_PER_KG = 35.27396195  # base metals are quoted per (avoirdupois) ounce
LIVE_SOURCE_PREFIX = f"Live: {PROVIDER}"
STALE_AFTER = timedelta(hours=12)


@dataclass(frozen=True)
class LiveRule:
    symbol: str
    scrap_share: float  # scrap value as a share of pure-metal value
    margin: float  # fair trader margin taken off the scrap price
    plausible: tuple[float, float]  # INR/kg bounds for the final reference price

    def describe(self) -> str:
        return (f"{self.symbol} market price x {self.scrap_share:.0%} scrap value "
                f"- {self.margin:.0%} trader margin")


# material name -> rule. Add more when a material with a market feed is tracked.
LIVE_RULES: dict[str, LiveRule] = {
    "Copper": LiveRule(symbol="XCU", scrap_share=0.90, margin=0.10, plausible=(300, 2000)),
}


class LiveUnavailable(Exception):
    pass


def api_key() -> str | None:
    return env_value(KEY_NAME)


def fetch_inr_per_kg(symbols: list[str], key: str, client: httpx.Client | None = None) -> dict[str, float]:
    """Market price in INR per kg for each metal symbol."""
    http = client or httpx.Client(timeout=15)
    try:
        r = http.get(PROVIDER_URL, params={"api_key": key, "base": "INR", "currencies": ",".join(symbols)})
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise LiveUnavailable(f"{PROVIDER} not reachable: {e.__class__.__name__}") from e
    if not data.get("success"):
        err = data.get("error") or {}
        raise LiveUnavailable(f"{PROVIDER} refused the request: {err.get('info') or err or r.status_code}")
    rates = data.get("rates") or {}
    out = {}
    for sym in symbols:
        per_oz = rates.get(f"INR{sym}")  # INR per ounce, when the API provides it directly
        if per_oz is None and rates.get(sym):
            per_oz = 1 / rates[sym]  # rates[sym] = ounces per 1 INR
        if per_oz:
            out[sym] = per_oz * OZ_PER_KG
    return out


def reference_price(rule: LiveRule, market_inr_per_kg: float) -> float:
    return round(market_inr_per_kg * rule.scrap_share * (1 - rule.margin))


def last_live_update(session: Session) -> PriceUpdate | None:
    q = select(PriceUpdate).where(PriceUpdate.source.startswith(LIVE_SOURCE_PREFIX))
    return session.exec(q.order_by(PriceUpdate.ts.desc())).first()


def refresh_live(session: Session, key: str | None = None, client: httpx.Client | None = None,
                 now: datetime | None = None, write_csv: bool = True) -> dict:
    """Fetch live metal prices and update the materials that have a live rule."""
    key = key or api_key()
    if not key:
        return {"configured": False, "results": [],
                "message": f"No {KEY_NAME}. Get a free key at metalpriceapi.com and put "
                           f"{KEY_NAME}=... in backend/.env. Manual prices stay in use."}
    now = now or datetime.now(IST)
    materials = {m.name: m for m in session.exec(select(Material))}
    rules = {name: rule for name, rule in LIVE_RULES.items() if name in materials}
    try:
        market = fetch_inr_per_kg(sorted({r.symbol for r in rules.values()}), key, client)
        error = None
    except LiveUnavailable as e:
        market, error = {}, str(e)

    results = []
    for name, rule in rules.items():
        m = materials[name]
        base = {"material": name, "old_price": m.ref_price_per_kg, "new_price": m.ref_price_per_kg}
        if error or rule.symbol not in market:
            results.append({**base, "status": "kept",
                            "detail": error or f"{PROVIDER} returned no {rule.symbol} price"})
            continue
        price = reference_price(rule, market[rule.symbol])
        lo, hi = rule.plausible
        if not lo <= price <= hi:
            results.append({**base, "status": "rejected",
                            "detail": f"computed Rs {price:,.0f}/kg is outside the believable "
                                      f"Rs {lo:,.0f}-{hi:,.0f}/kg range; kept the last price"})
            continue
        source = (f"{LIVE_SOURCE_PREFIX} {rule.symbol} Rs {market[rule.symbol]:,.0f}/kg "
                  f"x {rule.scrap_share:.0%} scrap - {rule.margin:.0%} margin")
        set_price(session, m, price, source, now=now, write_csv=write_csv)
        results.append({**base, "new_price": price, "status": "updated",
                        "detail": f"market Rs {market[rule.symbol]:,.0f}/kg -> {rule.describe()}"})
    return {"configured": True, "results": results, "message": error or "ok"}


def refresh_if_stale(session: Session, now: datetime | None = None) -> dict | None:
    """Used at API start: refresh only when a key is set and the last live price is old."""
    if not api_key():
        return None
    now = now or datetime.now(IST)
    last = last_live_update(session)
    if last is not None and now - last.ts.astimezone(IST) < STALE_AFTER:
        return None
    return refresh_live(session, now=now)
