"""SQLAlchemy 2.0 engine + session scope. Connection-config only — no schema here."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def get_engine(url: str, *, echo: bool = False) -> Engine:
    """Build a SQLAlchemy engine for the brain DB.

    Args:
        url: postgresql+psycopg://... connection string
        echo: emit SQL to stdout (useful during development)
    """
    return create_engine(url, echo=echo, future=True, pool_pre_ping=True)


_session_factories: dict[int, sessionmaker[Session]] = {}


def _factory_for(engine: Engine) -> sessionmaker[Session]:
    key = id(engine)
    if key not in _session_factories:
        _session_factories[key] = sessionmaker(bind=engine, expire_on_commit=False)
    return _session_factories[key]


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """Transactional scope. Commit on clean exit, rollback on exception."""
    session = _factory_for(engine)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
