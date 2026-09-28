"""Material passport: the auditable record of one collected lot and its custody chain.

Plain JSON (no blockchain). Carries no phone or Aadhaar data because the
passport travels downstream to aggregators, recyclers and producers.
"""
import hashlib
import json
from datetime import datetime

from app.models import IST, Aggregator, Collector, Material, MaterialPassport, Recycler, Transaction

PASSPORT_VERSION = "mitra.passport/v1"


def ist(ts: datetime) -> str:
    return ts.astimezone(IST).isoformat()


def photo_hash(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data else None


def passport_id(transaction_id: int) -> str:
    return f"MITRA-P-{transaction_id:06d}"


def custody_chain(
    tx: Transaction,
    collector: Collector,
    aggregator: Aggregator | None,
    passport: MaterialPassport | None,
) -> list[dict]:
    """Recorded chain if a passport exists, else the hops known from the transaction."""
    if passport is not None:
        return json.loads(passport.chain_json)
    chain = [{"stage": "collector", "id": collector.id, "name": collector.name,
              "area": collector.area, "ts": ist(tx.ts)}]
    if aggregator is not None:
        # Assigned buyer; handover not yet recorded, so no timestamp.
        chain.append({"stage": "aggregator", "id": aggregator.id, "name": aggregator.name,
                      "reg_no": aggregator.cpcb_reg_no, "ts": None})
    return chain


def build_passport(
    tx: Transaction,
    collector: Collector,
    material: Material,
    aggregator: Aggregator | None = None,
    passport: MaterialPassport | None = None,
    recycler: Recycler | None = None,
    photo_sha256: str | None = None,
) -> dict:
    status = passport.status if passport is not None else "collected"
    has_gps = tx.gps_lat is not None and tx.gps_lon is not None
    return {
        "passport_version": PASSPORT_VERSION,
        "passport_id": passport_id(tx.id),
        "transaction_id": tx.id,
        "status": status,
        "custody_complete": status == "delivered",
        "collected_at": ist(tx.ts),
        "collector": {"id": collector.id, "name": collector.name, "area": collector.area},
        "material": {"name": material.name, "category": material.category,
                     "ref_price_per_kg": tx.ref_price_per_kg if tx.ref_price_per_kg is not None
                     else material.ref_price_per_kg},
        "weight_kg": tx.weight_kg,
        "amount_paid": tx.amount_paid,
        "gps": {"lat": tx.gps_lat, "lon": tx.gps_lon} if has_gps else None,
        "photo_sha256": photo_sha256,
        "classification": {
            "confirmed_by": "collector",
            "cv_suggested": tx.cv_suggested,
            "cv_confidence": tx.cv_confidence,
        },
        "chain": custody_chain(tx, collector, aggregator, passport),
        "destination": (
            {"recycler_id": recycler.id, "name": recycler.name, "cpcb_reg_no": recycler.cpcb_reg_no}
            if recycler is not None else None
        ),
    }
