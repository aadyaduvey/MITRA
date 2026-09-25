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
