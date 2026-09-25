"""SQLite engine + session. Default DB lives at backend/data/mitra.db.

Override with the MITRA_DB_URL env var (tests use an in-memory database).
"""
import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_DB_URL = f"sqlite:///{(DATA_DIR / 'mitra.db').as_posix()}"


def make_engine(url: str | None = None) -> Engine:
    url = url or os.environ.get("MITRA_DB_URL", DEFAULT_DB_URL)
    return create_engine(url, connect_args={"check_same_thread": False})


engine = make_engine()


def create_db_and_tables(bind: Engine = engine) -> None:
    from app import models  # noqa: F401  (registers tables on SQLModel.metadata)

    SQLModel.metadata.create_all(bind)


def drop_all(bind: Engine = engine) -> None:
    from app import models  # noqa: F401

    SQLModel.metadata.drop_all(bind)


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with Session(engine) as session:
        yield session
