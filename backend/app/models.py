"""SQLModel tables. Mirrors the canonical data model in CLAUDE.md.

Addition beyond the canonical model: a `recycler` table, which
material_passport.recycler_id points at. EPR output needs each destination
recycler's name and CPCB registration number.

All timestamps are timezone-aware; SQLModel stores them as UTC and returns
them in UTC. Anything we emit (passports, reports) is converted to IST.
"""
from datetime import datetime, timedelta, timezone

from sqlmodel import Field, SQLModel

IST = timezone(timedelta(hours=5, minutes=30))


class Collector(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    phone: str | None = Field(default=None, index=True, unique=True)  # optional via chat signup
    area: str
    aadhaar_last4: str | None = Field(default=None, max_length=4)
    registered_ts: datetime


class Material(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True)
    category: str = Field(index=True)  # pet | hdpe | paper | glass | metal | ewaste
    ref_price_per_kg: float


class Aggregator(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    area: str
    cpcb_reg_no: str


class Recycler(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    area: str
    cpcb_reg_no: str
    categories: str  # comma-separated material categories it is authorised for


class Transaction(SQLModel, table=True):
    __tablename__ = "transaction"

    id: int | None = Field(default=None, primary_key=True)
    collector_id: int = Field(foreign_key="collector.id", index=True)
    material_id: int = Field(foreign_key="material.id", index=True)
    weight_kg: float
    amount_paid: float
    gps_lat: float | None = None  # nullable: a chat log may arrive without location
    gps_lon: float | None = None
    photo_url: str | None = None
    cv_suggested: str | None = None
    cv_confidence: float | None = None
    ts: datetime = Field(index=True)
    aggregator_id: int | None = Field(default=None, foreign_key="aggregator.id")
    # reference price shown to the collector when the lot was logged; later price
    # changes must not rewrite past receipts (null only on databases created before this)
    ref_price_per_kg: float | None = None


class PriceUpdate(SQLModel, table=True):
    """History of reference-price changes (manual or live feed)."""
    __tablename__ = "price_update"

    id: int | None = Field(default=None, primary_key=True)
    material_id: int = Field(foreign_key="material.id", index=True)
    price_per_kg: float
    previous_price: float | None = None
    source: str  # who/what set it, e.g. "Jaipur kabadi market" or "Live: MetalpriceAPI ..."
    ts: datetime = Field(index=True)


class MaterialPassport(SQLModel, table=True):
    __tablename__ = "material_passport"

    id: int | None = Field(default=None, primary_key=True)
    transaction_id: int = Field(foreign_key="transaction.id", unique=True)
    chain_json: str  # JSON list of custody hops: collector -> aggregator -> recycler
    recycler_id: int | None = Field(default=None, foreign_key="recycler.id")
    status: str  # in_transit | delivered
