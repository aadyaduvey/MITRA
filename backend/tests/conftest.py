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


# Fixed prices for tests: tests must not depend on the real price file, which people edit.
TEST_PRICES_CSV = """material,category,ref_price_per_kg,source,updated_on
PET plastic,pet,12,Indicative FY24-25 estimate (PoC default),
HDPE,hdpe,14,Indicative FY24-25 estimate (PoC default),
Cardboard/paper,paper,9,Indicative FY24-25 estimate (PoC default),
Glass,glass,2,Indicative FY24-25 estimate (PoC default),
Metal (steel/aluminium blended),metal,40,Indicative FY24-25 estimate (PoC default),
Copper,metal,400,Indicative FY24-25 estimate (PoC default),
E-waste,ewaste,25,Indicative FY24-25 estimate (PoC default),
"""


@pytest.fixture(scope="session", autouse=True)
def fixed_test_prices(tmp_path_factory):
    """Point the whole test session at the fixed price list (before any DB is seeded)."""
    from app.engine import pricing

    path = tmp_path_factory.mktemp("prices") / "commodity_prices.csv"
    path.write_text(TEST_PRICES_CSV, encoding="utf-8")
    real = pricing.PRICES_CSV
    pricing.PRICES_CSV = path
    yield path
    pricing.PRICES_CSV = real


@pytest.fixture(autouse=True)
def isolate_prices_and_secrets(tmp_path, monkeypatch, fixed_test_prices):
    """Each test gets its own copy of the fixed prices (writes never leak between tests or
    reach the real file) and never reads real keys from backend/.env."""
    from app import config
    from app.engine import pricing

    csv_copy = tmp_path / "commodity_prices.csv"
    csv_copy.write_text(TEST_PRICES_CSV, encoding="utf-8")
    monkeypatch.setattr(pricing, "PRICES_CSV", csv_copy)
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "no.env")
    for name in ("METAL_PRICE_API_KEY", "TELEGRAM_TOKEN"):
        monkeypatch.delenv(name, raising=False)
