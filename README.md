# MITRA: Material Intelligence, Traceability & Recovery Architecture

**SIH26229, Kabadiwala Connect** (Ministry of Mines): bringing India's informal waste
collectors into the formal recycling chain.

MITRA is a traceability and EPR-compliance data layer. A kabadiwala registers and logs
each lot **by chat, with no app to install**. Every kg becomes a *material passport* that follows it
to a CPCB-authorised recycler. From that data the Ministry sees first-mile
**urban-mining intelligence** (how much copper, aluminium and e-waste is recovered, and
where), and producers get **EPR reports** in the format they file with CPCB.

> Everything in the demo database is synthetic. Aggregator and recycler names say "(synthetic)".

## Start it (one command)

**Windows**
```powershell
.\start.cmd              # installs what is missing, seeds demo data, opens the dashboard
.\start.cmd -Smoke       # checks every part and prints PASS/FAIL, then stops
.\start.cmd -Reseed      # fresh demo data (removes lots logged during rehearsal)
```
**macOS / Linux**: `./start.sh` (same options: `--smoke`, `--reseed`).

Needs [uv](https://docs.astral.sh/uv/) and Node 18+ with pnpm (`npm install -g pnpm`).
The first run downloads about 1 GB of packages (mostly PyTorch). After that it starts in about 30 seconds.

| What | Where |
|---|---|
| Dashboard | http://localhost:5173 |
| API docs | http://localhost:8000/docs |
| Telegram bot | starts automatically if `backend/.env` contains `TELEGRAM_TOKEN=...` ([setup](backend/README.md#telegram-bot-m5)) |
| Logs | `logs/` |

Ctrl+C stops everything.

## The 3-minute demo

| # | Do | Say |
|---|---|---|
| 1 | Phone, Telegram: `/start` → name → area. The bot replies with a **Collector ID** | "Digital identity for a kabadiwala in 20 seconds. No app, no form." |
| 2 | **📦 Log material** → send a photo of a can → the bot suggests *metal* → tap **Copper** → `3.5` → **📍 Share location** | "The camera only suggests; the collector confirms. He sees the fair price: ₹400/kg, ₹1,400." |
| 3 | Dashboard **Collector Map**: the lot appears within ~5 s, outlined orange; click it for the passport | "First-mile material data, captured with zero app install." |
| 4 | **Material Flow** | "kg flowing from collectors through aggregators to authorised recyclers, by material. This view does not exist today." |
| 5 | **Ministry Overview** | "₹88k of metal-bearing material: 59% of the value from 22% of the weight. This is the urban-mining signal the Ministry cannot see today." |
| 6 | **EPR Compliance** → **Download PDF** | "What a producer files with CPCB: collector IDs, material, weight, recycler, CPCB number." |

**No internet at the venue?** Replace steps 1-2 with
`cd backend; uv run python -m app.bot.offline_demo`. It runs the same conversation with the
same wording and the same API calls, and it includes a real test photo.

## How it fits together

```
 Telegram (collector's phone)                         Browser (Ministry / producer)
        │                                                        │
   bot (python-telegram-bot) ──HTTP──►  FastAPI  ◄──HTTP──  React dashboard
                                          │   │                  (map, flow, EPR, overview)
                        engine (pure) ────┘   └──── photo classifier (MobileNetV3, suggestion only)
               pricing · material flow · passport · EPR · summary
                                          │
                                   SQLite (SQLModel) ──► EPR PDF / CSV / JSON
```

Stack: Python 3.11, FastAPI, SQLModel, SQLite, python-telegram-bot, PyTorch/torchvision,
reportlab · React, Vite, TypeScript, Tailwind, Recharts, Leaflet.

## Design rules it keeps

- **No app download.** Onboarding and logging happen in Telegram chat.
- **The camera suggests, the collector decides.** The suggestion is stored next to the confirmed material, so overrides are auditable.
- **A fair reference price per kg** is shown at every step.
- **Plain PDF / CSV / JSON output, no blockchain** (CPCB does not accept it).
- **Right to erasure (DPDP Act):** `/forget` deletes the person and keeps the anonymous material record that filed reports depend on.

## Repository

```
start.cmd / start.ps1 / start.sh   one-command start
backend/    API, engine, seed, EPR PDF, Telegram bot, photo classifier, tests   (backend/README.md)
frontend/   dashboard                                                          (frontend/README.md)
CLAUDE.md   project constitution
QA_REPORT.md   test results, edge cases, known limitations
```

Tests: `cd backend; uv run pytest` (113 tests, no network) · `cd frontend; pnpm build; pnpm lint`.
Results and known limitations: [QA_REPORT.md](QA_REPORT.md).
