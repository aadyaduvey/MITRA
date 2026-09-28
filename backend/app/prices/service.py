"""Set and read reference prices. Every change is kept in `price_update` and written back
to commodity_prices.csv, so a reseed starts from the latest prices."""
from datetime import datetime

from sqlmodel import Session, select

from app.engine import pricing
from app.models import IST, Material, PriceUpdate

MAX_PRICE = 100_000  # INR/kg; anything above is a typo


class PriceError(ValueError):
    pass


def find_material(session: Session, key: str | int) -> Material:
    """By id, exact name, or a unique start of the name (case-insensitive): 'cop' -> Copper."""
    materials = list(session.exec(select(Material).order_by(Material.id)))
    if isinstance(key, int) or str(key).isdigit():
        found = [m for m in materials if m.id == int(key)]
    else:
        k = str(key).strip().casefold()
        found = [m for m in materials if m.name.casefold() == k] or \
                [m for m in materials if m.name.casefold().startswith(k)]
    if len(found) != 1:
        names = ", ".join(m.name for m in materials)
        why = "matches several materials" if found else "matches no material"
        raise PriceError(f"'{key}' {why}. Materials: {names}")
    return found[0]


def set_price(session: Session, material: Material, price: float, source: str,
              now: datetime | None = None, write_csv: bool = True) -> PriceUpdate:
    if not 0 < price <= MAX_PRICE:
        raise PriceError(f"price must be between 0 and {MAX_PRICE:,} INR/kg, got {price}")
    source = " ".join(source.split())
    if len(source) < 2:
        raise PriceError("say where the price comes from (source), e.g. 'Jaipur kabadi market'")
    now = (now or datetime.now(IST)).replace(microsecond=0)
    update = PriceUpdate(material_id=material.id, price_per_kg=round(price, 2),
                         previous_price=material.ref_price_per_kg, source=source, ts=now)
    material.ref_price_per_kg = round(price, 2)
    session.add_all([material, update])
    session.commit()
    session.refresh(update)
    if write_csv:
        try:
            pricing.save_price(material.name, material.ref_price_per_kg, source, now.date().isoformat())
        except pricing.UnknownMaterial:
            pass  # material added outside the CSV: the database is still updated
    return update


def ensure_price_history(session: Session, now: datetime | None = None) -> int:
    """Databases created before price history existed get one starting row per material
    (source taken from the price file). Returns how many rows were added."""
    if session.exec(select(PriceUpdate)).first() is not None:
        return 0
    prices = pricing.load_prices()
    now = (now or datetime.now(IST)).replace(microsecond=0)
    rows = []
    for m in session.exec(select(Material)):
        p = prices.get(m.name)
        when = datetime.fromisoformat(p.updated_on).replace(tzinfo=IST) if p and p.updated_on else now
        rows.append(PriceUpdate(material_id=m.id, price_per_kg=m.ref_price_per_kg,
                                source=(p.source if p and p.source else "commodity_prices.csv"), ts=when))
    session.add_all(rows)
    session.commit()
    return len(rows)


def latest_updates(session: Session) -> dict[int, PriceUpdate]:
    """Most recent price change per material id."""
    latest: dict[int, PriceUpdate] = {}
    for u in session.exec(select(PriceUpdate).order_by(PriceUpdate.ts, PriceUpdate.id)):
        latest[u.material_id] = u
    return latest


def history(session: Session, material_id: int | None = None, limit: int = 100) -> list[PriceUpdate]:
    q = select(PriceUpdate)
    if material_id is not None:
        q = q.where(PriceUpdate.material_id == material_id)
    return list(session.exec(q.order_by(PriceUpdate.ts.desc(), PriceUpdate.id.desc()).limit(limit)))
