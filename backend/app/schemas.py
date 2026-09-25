"""Pydantic request/response models. Routes return these, never ORM objects.

All timestamps in responses are IST (+05:30).
"""
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------- collectors ----------


class CollectorCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    area: str = Field(min_length=2, max_length=60)
    phone: str | None = Field(default=None, description="Indian mobile; normalised to +91XXXXXXXXXX")
    aadhaar_last4: str | None = Field(default=None, pattern=r"^\d{4}$")

    @field_validator("name", "area")
    @classmethod
    def strip(cls, v: str) -> str:
        return " ".join(v.split())

    @field_validator("phone")
    @classmethod
    def normalise_phone(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        digits = re.sub(r"\D", "", v)
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        if len(digits) != 10 or digits[0] not in "6789":
            raise ValueError("phone must be a 10-digit Indian mobile number")
        return "+91" + digits


class CollectorOut(BaseModel):
    id: int
    code: str  # human-friendly ID shown to the collector, e.g. MITRA-C-000041
    name: str
    area: str
    phone: str | None
    registered_ts: datetime


class CollectorSummary(CollectorOut):
    lots: int
    kg: float
    last_ts: datetime | None
    last_lat: float | None
    last_lon: float | None


# ---------- materials / transactions ----------


class MaterialOut(BaseModel):
    id: int
    name: str
    category: str
    ref_price_per_kg: float


class TransactionCreate(BaseModel):
    collector_id: int
    material_id: int = Field(description="Material the collector CONFIRMED (may differ from cv_suggested)")
    weight_kg: float = Field(gt=0, le=2000)
    amount_paid: float | None = Field(default=None, ge=0,
                                      description="Defaults to weight x reference price")
    gps_lat: float | None = Field(default=None, ge=-90, le=90)
    gps_lon: float | None = Field(default=None, ge=-180, le=180)
    photo_url: str | None = Field(default=None, max_length=500)
    cv_suggested: str | None = Field(default=None, max_length=40)
    cv_confidence: float | None = Field(default=None, ge=0, le=1)
    aggregator_id: int | None = None
    ts: datetime | None = Field(default=None, description="Defaults to now; naive values are read as IST")

    @model_validator(mode="after")
    def gps_pair(self) -> "TransactionCreate":
        if (self.gps_lat is None) != (self.gps_lon is None):
            raise ValueError("gps_lat and gps_lon must be given together")
        return self


class TransactionOut(BaseModel):
    id: int
    collector_id: int
    collector_name: str
    material_id: int
    material: str
    category: str
    weight_kg: float
    amount_paid: float
    ref_price_per_kg: float
    ref_amount: float  # weight x reference price: what a fair payout looks like
    gps_lat: float | None
    gps_lon: float | None
    photo_url: str | None
    cv_suggested: str | None
    cv_confidence: float | None
    ts: datetime
    aggregator_id: int | None
    passport_id: str
    passport_status: str


class CollectorDetail(CollectorSummary):
    recent_transactions: list[TransactionOut]


# ---------- passport ----------


class ChainHop(BaseModel):
    stage: Literal["collector", "aggregator", "recycler"]
    id: int
    name: str
    area: str | None = None
    reg_no: str | None = None
    cpcb_reg_no: str | None = None
    ts: str | None  # ISO; null = handover not yet recorded


class PassportCollector(BaseModel):
    id: int
    name: str
    area: str


class PassportMaterial(BaseModel):
    name: str
    category: str
    ref_price_per_kg: float


class Gps(BaseModel):
    lat: float
    lon: float


class Classification(BaseModel):
    confirmed_by: str
    cv_suggested: str | None
    cv_confidence: float | None


class Destination(BaseModel):
    recycler_id: int
    name: str
    cpcb_reg_no: str


class PassportOut(BaseModel):
    passport_version: str
    passport_id: str
    transaction_id: int
    status: str
    custody_complete: bool
    collected_at: str
    collector: PassportCollector
    material: PassportMaterial
    weight_kg: float
    amount_paid: float
    gps: Gps | None
    photo_sha256: str | None
    classification: Classification
    chain: list[ChainHop]
    destination: Destination | None


# ---------- EPR ----------


class Period(BaseModel):
    start: str
    end: str


class EprTotals(BaseModel):
    lots: int
    collectors: int
    kg_collected: float
    kg_in_transit: float
    kg_delivered: float


class EprMaterialRow(BaseModel):
    material: str
    category: str
    lots: int
    kg_collected: float
    kg_in_transit: float
    kg_delivered: float


class EprRecyclerRow(BaseModel):
    name: str
    cpcb_reg_no: str | None
    lots: int
    kg_in_transit: float
    kg_delivered: float
    kg_by_material: dict[str, float]


class EprLotOut(BaseModel):
    passport_id: str
    transaction_id: int
    collector_id: int
    collected_at: str
    material: str
    category: str
    kg: float
    aggregator: str | None
    recycler: str | None
    recycler_cpcb_reg_no: str | None
    status: str
    delivered_at: str | None


class EprReport(BaseModel):
    period: Period
    generated_at: str
    totals: EprTotals
    by_material: list[EprMaterialRow]
    recyclers: list[EprRecyclerRow]
    collector_ids: list[int]
    lots: list[EprLotOut]  # lots with a verified recycler (delivered or in transit)


# ---------- ministry ----------


class SummaryTotals(BaseModel):
    kg: float
    lots: int
    value_at_ref_inr: float
    amount_paid_inr: float
    active_collectors: int
    registered_collectors: int
    kg_traced: float
    pct_traced: float


class SummaryMaterialRow(BaseModel):
    material: str
    category: str
    kg: float
    lots: int
    value_at_ref_inr: float


class SummaryAreaRow(BaseModel):
    area: str
    kg: float
    lots: int
    collectors: int
    lat: float | None
    lon: float | None


class MetalMaterialRow(BaseModel):
    material: str
    kg: float
    value_at_ref_inr: float


class MetalRecovery(BaseModel):
    kg: float
    value_at_ref_inr: float
    pct_of_total_value: float
    materials: list[MetalMaterialRow]


class MinistrySummary(BaseModel):
    period: Period | None  # null = all recorded data
    totals: SummaryTotals
    by_material: list[SummaryMaterialRow]
    by_category: dict[str, float]
    by_area: list[SummaryAreaRow]
    metal_recovery: MetalRecovery


# ---------- flow ----------


class SankeyNode(BaseModel):
    name: str
    stage: Literal["collector", "aggregator", "recycler", "pending"]


class SankeyLink(BaseModel):
    source: int
    target: int
    material: str
    value: float  # kg


class Sankey(BaseModel):
    nodes: list[SankeyNode]
    links: list[SankeyLink]
    kg_total: float
    kg_traced: float
    pct_traced: float
