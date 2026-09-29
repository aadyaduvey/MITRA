"""FastAPI app entry: uv run uvicorn app.main:app --reload --port 8000"""
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    routes_classify,
    routes_collectors,
    routes_epr,
    routes_ministry,
    routes_passport,
    routes_prices,
    routes_transactions,
)
from app.db import create_db_and_tables, engine
from app.remote import RemoteReadOnly

DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_db_and_tables()  # creates missing tables/columns; never seeds or wipes
    # live metal prices in the background (only if METAL_PRICE_API_KEY is set and prices are stale)
    threading.Thread(target=routes_prices.refresh_on_startup, args=(engine,), daemon=True).start()
    yield


app = FastAPI(title="MITRA", version="0.1.0",
              description="Material traceability + EPR compliance API", lifespan=lifespan)
app.add_middleware(RemoteReadOnly)  # shared links can view, only the laptop can change data
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("MITRA_CORS_ORIGINS", DEFAULT_ORIGINS).split(","),
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
for r in (routes_collectors, routes_transactions, routes_passport, routes_epr, routes_ministry,
          routes_classify, routes_prices):
    app.include_router(r.router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
