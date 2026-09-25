from datetime import datetime

import pytest
from sqlmodel import Session

from app.db import make_engine
from app.seed import IST, reseed

SEED_END = datetime(2026, 9, 26, 20, 0, tzinfo=IST)


@pytest.fixture(scope="session")
def seeded_engine():
    """In-memory SQLite, seeded once per test session. Never touches mitra.db."""
    from sqlalchemy.pool import StaticPool
    from sqlmodel import create_engine

    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    reseed(eng, end=SEED_END)
    return eng


@pytest.fixture
def session(seeded_engine):
    with Session(seeded_engine) as s:
        yield s
