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
