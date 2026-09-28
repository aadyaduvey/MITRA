from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.db import get_session
from app.main import app
from app.seed import IST, reseed

SEED_END = datetime(2026, 9, 26, 20, 0, tzinfo=IST)


@pytest.fixture(scope="session")
def seeded_engine():
    """In-memory SQLite, seeded once per test session. Never touches mitra.db."""
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    reseed(eng, end=SEED_END)
    return eng


@pytest.fixture
def session(seeded_engine):
    with Session(seeded_engine) as s:
        yield s


@pytest.fixture
def client():
    """API over HTTP (httpx TestClient) backed by a fresh seeded in-memory DB."""
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    reseed(eng, end=SEED_END)

    def session_override():
        with Session(eng) as s:
            yield s

    app.dependency_overrides[get_session] = session_override
    yield TestClient(app)  # no `with`: lifespan (which touches mitra.db) does not run
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def isolate_prices_and_secrets(tmp_path, monkeypatch):
    """Tests never write the real price file or read real keys from backend/.env."""
    import shutil

    from app import config
    from app.engine import pricing

    csv_copy = tmp_path / "commodity_prices.csv"
    shutil.copy(pricing.PRICES_CSV, csv_copy)
    monkeypatch.setattr(pricing, "PRICES_CSV", csv_copy)
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "no.env")
    for name in ("METAL_PRICE_API_KEY", "TELEGRAM_TOKEN"):
        monkeypatch.delenv(name, raising=False)
