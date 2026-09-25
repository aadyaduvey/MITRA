# MITRA — Project Constitution

## What this is
A material-traceability and EPR-compliance data layer between India's informal
waste collectors (kabadiwalas) and the formal recycling chain. NOT a consumer
scrap-pickup app (that is ScrapUncle's space). The customer is the Ministry of
Mines and CPCB: the product is auditable first-mile material-flow intelligence.

## The three pillars
1. Digital identity for informal collectors (low-friction, via chat, no app install).
2. Transaction-level traceability: every kg logged with collector, material,
   weight, GPS, timestamp, photo -> a "material passport" -> chain of custody
   to a CPCB-authorized recycler.
3. EPR compliance output: reports producers/CPCB can use, in their format.

## Non-negotiable design rules
- Onboarding must NOT require an app download. Use a chat bot (Telegram for PoC).
- CV material classification is a SUGGESTION the collector confirms, never
  autonomous. Always allow manual override via dropdown.
- Commodity reference price = MCX/wholesale spot minus intermediary margins,
  shown per kg. Kills household information asymmetry.
- EPR output is standard CSV/PDF/JSON. NO blockchain: CPCB does not accept it.

## Stack (do not change without being told)
Backend: Python 3.11, FastAPI, SQLModel, SQLite. Bot: python-telegram-bot.
CV: PyTorch MobileNetV3 on TrashNet. Reports: reportlab.
Frontend: React + Vite + TS + Recharts + Leaflet + Tailwind.

## Build order (backwards from bot + model)
1 data models  2 synthetic seed  3 pricing + flow engine + passport  4 API + EPR PDF
5 dashboard  6 Telegram bot  7 CV classifier.
The system must be fully demoable on seeded data before the bot and model exist.

## Data model (canonical)
collector(id, name, phone, area, aadhaar_last4, registered_ts)
material(id, name, category, ref_price_per_kg)
aggregator(id, name, area, cpcb_reg_no)
transaction(id, collector_id, material_id, weight_kg, amount_paid, gps_lat,
            gps_lon, photo_url, cv_suggested, cv_confidence, ts, aggregator_id)
material_passport(id, transaction_id, chain_json, recycler_id, status)

## Material categories (PoC, 6 classes matching TrashNet)
PET plastic, HDPE, cardboard/paper, glass, metal (steel/aluminium/copper), e-waste.

## Conventions
- Every engine function is pure and unit-tested with a tiny fixture.
- API returns typed Pydantic schemas, never raw ORM objects.
- No secrets in code (Telegram token via env var). No network calls in tests.
- Keep functions small. Commit after each passing acceptance gate.

## What "done" means
A milestone is done only when its acceptance gate (defined by the human) passes
when run locally. Never self-certify. Never fake data to pass a gate.

## Framing for the Ministry of Mines
Lead with metal/mineral recovery and urban mining, not just "waste". The
ministry cares about copper/aluminium/rare-earth flows through the informal
chain. Every transaction is a data point on recoverable material at national scale.
