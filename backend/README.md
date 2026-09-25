# MITRA backend

FastAPI + SQLModel + SQLite. See `../CLAUDE.md`.

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

## Data (M1)

```bash
uv run python -m app.seed   # wipe + reseed backend/data/mitra.db, prints row counts
uv run pytest               # tests use an in-memory DB; never touch mitra.db
```

Seed data is synthetic (names, phones, Aadhaar digits, aggregator/recycler
names and registration numbers are all invented) and deterministic: same rows
every run, with timestamps covering the 14 days before the reseed.
Reference prices live in `data/commodity_prices.csv` (indicative FY24-25, INR/kg).

## API (M3)

Start: `uv run uvicorn app.main:app --reload --port 8000`. Interactive docs at
http://localhost:8000/docs. All response timestamps are IST (+05:30).

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness |
| GET | `/api/materials` | material list + reference price/kg (bot/UI pickers) |
| POST | `/api/collectors` | register a collector (name, area, optional phone/aadhaar_last4) |
| DELETE | `/api/collectors/{id}` | right to erasure: deletes name, phone, Aadhaar digits and photos; lots stay, anonymous |
| GET | `/api/collectors`, `/api/collectors/{id}` | list with totals; detail with recent lots |
| POST | `/api/transactions` | log a lot; amount defaults to weight x reference price |
| GET | `/api/transactions` | lots for the map (`collector_id`, `start`, `end`, `limit`) |
| GET | `/api/passport/{transaction_id}` | material passport JSON |
| GET | `/api/epr/report` | EPR report, `format=json\|pdf\|csv`, `start`/`end` (default last 30 days) |
| GET | `/api/ministry/summary` | totals, material mix, geography, metal recovery |
| GET | `/api/flow/sankey` | Sankey nodes/links (`group_by=area\|collector`) |

curl (PowerShell: use `curl.exe`, not the `curl` alias):

```bash
curl -X POST localhost:8000/api/collectors -H "Content-Type: application/json" \
  -d '{"name":"Asha Devi","area":"Sanganer","phone":"9829012345"}'
curl -X POST localhost:8000/api/transactions -H "Content-Type: application/json" \
  -d '{"collector_id":41,"material_id":6,"weight_kg":3,"gps_lat":26.82,"gps_lon":75.79}'
curl localhost:8000/api/passport/25
curl "localhost:8000/api/epr/report?format=pdf" -o epr.pdf
curl localhost:8000/api/ministry/summary
```

## Telegram bot (M5)

Collectors register and log lots by chat. No app install. The bot talks only to
the API; its token comes from `TELEGRAM_TOKEN` (never committed).

**One-time setup**
1. On Telegram, message **@BotFather**, send `/newbot`, pick a name and a
   username ending in `bot`. Copy the token it gives you.
2. Put it in `backend/.env` (git-ignored) as `TELEGRAM_TOKEN=123456:ABC...`,
   or set it for the session: `$env:TELEGRAM_TOKEN = "123456:ABC..."` (PowerShell).

**Run** (API must already be running on :8000, laptop needs internet):
```powershell
cd D:\MITRA\backend
uv run python -m app.bot.telegram_bot
```

**Demo script** (send these from your phone, in order):

| # | You send / tap | Bot replies |
|---|---|---|
| 1 | `/start` | Namaste, asks your name (English + Hindi) |
| 2 | `Sunita Devi` | asks your area |
| 3 | `Raja Park` | "You are registered", **Collector ID MITRA-C-0000xx**, menu buttons appear |
| 4 | tap **📦 Log material** | material buttons with price per kg |
| 5 | tap **Copper · ₹400/kg** | "How many kg?" |
| 6 | `3.5` | asks for a photo |
| 7 | send a photo, or tap **Skip photo** | asks for location |
| 8 | tap **📍 Share location** | receipt: passport ID, ₹400/kg, fair value ₹1,400, "now on the MITRA map" |
| 9 | on the dashboard, **Collector Map** | new lot outlined orange, first in **Latest lots** within ~5 s |

Extras: **💰 Today's prices** (or `/prices`) shows the reference price list;
`/cancel` stops a step; `/help` lists commands. `/forget` asks for confirmation, then
deletes the collector's name, phone, Aadhaar digits and photos (DPDP Act right to
erasure). Their past lots stay without a name, so filed EPR reports still add up. If you reseed the database,
the bot notices on the next `/start` and asks the collector to register again.

**No internet at the venue?** Run the same conversation in the terminal. It
uses the same wording and the same API calls, so the dashboard updates the same way:
```powershell
uv run python -m app.bot.offline_demo          # press Enter to advance each message
uv run python -m app.bot.offline_demo --auto   # no pauses
```
