"""Synthetic demo data: collectors, transactions and passports around Jaipur.

Everything here is clearly SYNTHETIC. Names, phone numbers, Aadhaar digits,
aggregator/recycler names and registration numbers are invented. Output is
deterministic for a given rng seed; timestamps are relative to `end`
(default: now), so the last 14 days always contain data. Times are generated
in IST (collection hours 07:00-19:00) and stored as UTC by SQLModel.

Wipe + reseed:  uv run python -m app.seed
"""
import csv
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlmodel import Session, func, select

from app.db import DATA_DIR, create_db_and_tables, drop_all, engine
from app.models import (
    Aggregator,
    Collector,
    Material,
    MaterialPassport,
    Recycler,
    Transaction,
)

PRICES_CSV = DATA_DIR / "commodity_prices.csv"
IST = timezone(timedelta(hours=5, minutes=30))

N_COLLECTORS = 40
N_TRANSACTIONS = 400
N_DAYS = 14
N_PASSPORTS = 15
JAIPUR_CENTER = (26.9, 75.8)
JAIPUR_SPREAD = 0.1  # every GPS point is clamped to centre +/- this

# Approximate locality centres (lat, lon). Collector home bases and transaction
# GPS are jittered around these, so a pin's area label matches where it sits.
AREAS = {
    "Malviya Nagar": (26.855, 75.815), "Mansarovar": (26.868, 75.760),
    "Vaishali Nagar": (26.912, 75.745), "Sanganer": (26.820, 75.790),
    "Jhotwara": (26.955, 75.740), "C-Scheme": (26.905, 75.805),
    "Raja Park": (26.900, 75.830), "Tonk Road": (26.875, 75.800),
    "Sitapura": (26.805, 75.850), "Johari Bazaar": (26.922, 75.826),
    "Bani Park": (26.930, 75.795), "Jagatpura": (26.830, 75.860),
    "Pratap Nagar": (26.810, 75.825), "Murlipura": (26.960, 75.770),
    "Vidhyadhar Nagar": (26.965, 75.790),
}
FIRST_NAMES = [
    "Ramesh", "Suresh", "Mahesh", "Rajesh", "Mukesh", "Dinesh", "Kailash",
    "Ramlal", "Shankar", "Gopal", "Mohan", "Babulal", "Sunita", "Kamla",
    "Geeta", "Meena", "Pooja", "Imran", "Salim", "Rafiq", "Anwar", "Farida",
]
LAST_NAMES = [
    "Kumar", "Meena", "Saini", "Gurjar", "Prajapat", "Verma", "Sharma",
    "Khan", "Qureshi", "Bairwa", "Yadav", "Devi", "Jangid", "Mali",
]

# (name, area, registration no.) - all invented for the PoC.
AGGREGATORS = [
    ("Sanganer Scrap Traders (synthetic)", "Sanganer", "RSPCB/AGG/2024/SYN-0101"),
    ("Jhotwara Kabadi Sangh (synthetic)", "Jhotwara", "RSPCB/AGG/2024/SYN-0102"),
    ("Pink City Material Hub (synthetic)", "Mansarovar", "RSPCB/AGG/2024/SYN-0103"),
]
# (name, area, CPCB reg no., authorised categories) - all invented.
RECYCLERS = [
    ("Sitapura Polymer Recyclers (synthetic)", "Sitapura RIICO",
     "CPCB/PWM/RJ/2024/SYN-2001", "pet,hdpe"),
    ("VKI Metal & E-Waste Recovery (synthetic)", "VKI Area",
     "CPCB/EWM/RJ/2024/SYN-2002", "metal,ewaste"),
    ("Bagru Fibre & Glass Recovery (synthetic)", "Bagru",
     "CPCB/SWM/RJ/2024/SYN-2003", "paper,glass"),
]

# Relative frequency and realistic (min, max) kg per lot, by material name.
MATERIAL_PROFILE = {
    "Cardboard/paper": (30, (5, 50)),
    "PET plastic": (22, (2, 25)),
    "Metal (steel/aluminium blended)": (16, (3, 40)),
    "HDPE": (12, (2, 25)),
    "Glass": (10, (5, 50)),
    "E-waste": (7, (2, 20)),
    "Copper": (3, (2, 8)),
}
# Collectors are paid slightly under reference price (intermediary margin).
PAYOUT_FACTOR = (0.85, 1.0)


def load_materials(path: Path = PRICES_CSV) -> list[Material]:
    with path.open(newline="", encoding="utf-8") as f:
        return [
            Material(
                name=row["material"],
                category=row["category"],
                ref_price_per_kg=float(row["ref_price_per_kg"]),
            )
            for row in csv.DictReader(f)
        ]


def make_collectors(rng: random.Random, end: datetime) -> list[tuple[Collector, tuple[float, float]]]:
    """Each collector gets a home base (lat, lon) used to place their transactions."""
    out = []
    phones: set[str] = set()
    for _ in range(N_COLLECTORS):
        phone = f"+9199{rng.randrange(10**8):08d}"
        while phone in phones:
            phone = f"+9199{rng.randrange(10**8):08d}"
        phones.add(phone)
        c = Collector(
            name=f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
            phone=phone,
            area=rng.choice(list(AREAS)),
            aadhaar_last4=f"{rng.randrange(10**4):04d}",
            registered_ts=end - timedelta(days=rng.randint(N_DAYS + 1, 180)),
        )
        base = jitter(rng, AREAS[c.area], 0.012)
        out.append((c, base))
    return out


def jitter(rng: random.Random, point: tuple[float, float], spread: float) -> tuple[float, float]:
    """Random point near `point`, rounded and clamped to the Jaipur PoC box."""
    lat0, lon0 = JAIPUR_CENTER
    lat = min(max(point[0] + rng.uniform(-spread, spread), lat0 - JAIPUR_SPREAD), lat0 + JAIPUR_SPREAD)
    lon = min(max(point[1] + rng.uniform(-spread, spread), lon0 - JAIPUR_SPREAD), lon0 + JAIPUR_SPREAD)
    return round(lat, 6), round(lon, 6)


def nearest(items: list, lat: float, lon: float, coords: list[tuple[float, float]]):
    d = [(la - lat) ** 2 + (lo - lon) ** 2 for la, lo in coords]
    return items[d.index(min(d))]


def collection_time(rng: random.Random, start: datetime, end: datetime) -> datetime:
    """Random time within [start, end], during collection hours (07:00-18:59)."""
    n_dates = (end.date() - start.date()).days + 1
    while True:
        day = start + timedelta(days=rng.randrange(n_dates))
        ts = day.replace(hour=rng.randint(7, 18), minute=rng.randrange(60), second=0, microsecond=0)
        if start <= ts <= end:
            return ts


def make_transactions(
    rng: random.Random,
    collectors: list[tuple[Collector, tuple[float, float]]],
    materials: list[Material],
    aggregators: list[Aggregator],
    agg_coords: list[tuple[float, float]],
    end: datetime,
) -> list[Transaction]:
    by_name = {m.name: m for m in materials}
    names = list(MATERIAL_PROFILE)
    freqs = [MATERIAL_PROFILE[n][0] for n in names]
    start = end - timedelta(days=N_DAYS)
    txs = []
    for _ in range(N_TRANSACTIONS):
        collector, (blat, blon) = rng.choice(collectors)
        mat = by_name[rng.choices(names, weights=freqs)[0]]
        lo, hi = MATERIAL_PROFILE[mat.name][1]
        weight = round(rng.uniform(lo, hi), 1)
        lat, lon = jitter(rng, (blat, blon), 0.008)
        ts = collection_time(rng, start, end)
        txs.append(
            Transaction(
                collector_id=collector.id,
                material_id=mat.id,
                weight_kg=weight,
                amount_paid=round(weight * mat.ref_price_per_kg * rng.uniform(*PAYOUT_FACTOR), 2),
                gps_lat=lat,
                gps_lon=lon,
                ts=ts,
                aggregator_id=nearest(aggregators, lat, lon, agg_coords).id,
            )
        )
    txs.sort(key=lambda t: t.ts)
    return txs


def build_chain(tx: Transaction, collector: Collector, agg: Aggregator, rec: Recycler,
                agg_ts: datetime, rec_ts: datetime) -> list[dict]:
    return [
        {"stage": "collector", "id": collector.id, "name": collector.name,
         "area": collector.area, "ts": tx.ts.isoformat()},
        {"stage": "aggregator", "id": agg.id, "name": agg.name,
         "reg_no": agg.cpcb_reg_no, "ts": agg_ts.isoformat()},
        {"stage": "recycler", "id": rec.id, "name": rec.name,
         "cpcb_reg_no": rec.cpcb_reg_no, "ts": rec_ts.isoformat()},
    ]


def make_passports(
    rng: random.Random,
    txs: list[Transaction],
    collectors: dict[int, Collector],
    materials: dict[int, Material],
    aggregators: dict[int, Aggregator],
    recyclers: list[Recycler],
    end: datetime,
) -> list[MaterialPassport]:
    """Multi-hop passports for a sample of lots, at least one per material."""
    picked: list[Transaction] = []
    for mid in materials:
        picked.append(rng.choice([t for t in txs if t.material_id == mid]))
    picked_ids = {t.id for t in picked}
    rest = [t for t in txs if t.id not in picked_ids]
    picked += rng.sample(rest, N_PASSPORTS - len(picked))

    passports = []
    for tx in sorted(picked, key=lambda t: t.id):
        cat = materials[tx.material_id].category
        rec = next(r for r in recyclers if cat in r.categories.split(","))
        agg_ts = tx.ts + timedelta(days=rng.randint(1, 2), hours=rng.randint(0, 6))
        rec_ts = agg_ts + timedelta(days=rng.randint(2, 4), hours=rng.randint(0, 6))
        chain = build_chain(tx, collectors[tx.collector_id], aggregators[tx.aggregator_id],
                            rec, agg_ts, rec_ts)
        passports.append(
            MaterialPassport(
                transaction_id=tx.id,
                chain_json=json.dumps(chain),
                recycler_id=rec.id,
                status="delivered" if rec_ts <= end else "in_transit",
            )
        )
    return passports


def seed(session: Session, *, rng_seed: int = 42, end: datetime | None = None) -> dict[str, int]:
    """Populate an empty database. Returns row counts."""
    rng = random.Random(rng_seed)
    end = (end or datetime.now(IST)).astimezone(IST).replace(microsecond=0)

    materials = load_materials()
    aggregators = [Aggregator(name=n, area=a, cpcb_reg_no=r) for n, a, r in AGGREGATORS]
    recyclers = [Recycler(name=n, area=a, cpcb_reg_no=r, categories=c) for n, a, r, c in RECYCLERS]
    collectors = make_collectors(rng, end)
    session.add_all(materials + aggregators + recyclers + [c for c, _ in collectors])
    session.flush()  # assign ids

    agg_coords = [AREAS[a.area] for a in aggregators]
    txs = make_transactions(rng, collectors, materials, aggregators, agg_coords, end)
    session.add_all(txs)
    session.flush()

    passports = make_passports(
        rng, txs,
        {c.id: c for c, _ in collectors},
        {m.id: m for m in materials},
        {a.id: a for a in aggregators},
        recyclers, end,
    )
    session.add_all(passports)
    session.commit()
    return counts(session)


def counts(session: Session) -> dict[str, int]:
    tables = [Collector, Material, Aggregator, Recycler, Transaction, MaterialPassport]
    return {t.__tablename__: session.exec(select(func.count()).select_from(t)).one() for t in tables}


def reseed(bind: Engine = engine, **kwargs) -> dict[str, int]:
    """Drop every table, recreate, and seed."""
    drop_all(bind)
    create_db_and_tables(bind)
    with Session(bind) as session:
        return seed(session, **kwargs)


def main() -> None:
    result = reseed()
    print(f"Reseeded {engine.url}")
    for table, n in result.items():
        print(f"  {table:<18} {n:>5}")


if __name__ == "__main__":
    main()
