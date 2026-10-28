from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import Settings


class Base(DeclarativeBase):
    pass


def build_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


settings = Settings.from_environment()
engine = build_engine(settings.database_url)
SessionLocal = build_session_factory(engine)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def initialize_database(target_engine: Engine = engine) -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(target_engine)


def mark_interrupted_analyses(target_engine: Engine = engine) -> None:
    from .models import AnalysisRun, utc_now

    with Session(target_engine) as session:
        session.execute(
            update(AnalysisRun)
            .where(AnalysisRun.status == "running")
            .values(status="interrupted", finished_at=utc_now())
        )
        session.commit()

