"""Database engine/session helpers."""
from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .base import Base


class Database:
    """Owns a lazily-created SQLAlchemy engine and session factory.

    Lazy construction matters for the application factory: importing
    ``app.main`` must not require the PostgreSQL driver when a test immediately
    creates its own isolated SQLite application instance.
    """

    def __init__(self, url: str, *, echo: bool = False):
        self.url = url
        self.echo = echo
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            kwargs: dict = {'future': True, 'echo': self.echo, 'pool_pre_ping': True}
            if self.url.startswith('sqlite'):
                kwargs['connect_args'] = {'check_same_thread': False}
                if ':memory:' in self.url:
                    kwargs['poolclass'] = StaticPool
            elif self.url.startswith('postgresql'):
                kwargs['connect_args'] = {'connect_timeout': 5}
            self._engine = create_engine(self.url, **kwargs)
            if self.url.startswith('sqlite'):
                @event.listens_for(self._engine, 'connect')
                def configure_sqlite(connection, record):
                    connection.execute('PRAGMA foreign_keys=ON')
                    connection.execute('PRAGMA busy_timeout=30000')
        return self._engine

    @property
    def session_factory(self) -> sessionmaker[Session]:
        if self._session_factory is None:
            self._session_factory = sessionmaker(
                bind=self.engine,
                class_=Session,
                expire_on_commit=False,
                autoflush=False,
                future=True,
            )
        return self._session_factory

    def create_schema(self) -> None:
        from . import models as _models  # noqa: F401
        from app.auth import rate_limit as _rate_limit  # noqa: F401
        Base.metadata.create_all(self.engine)

    def drop_schema(self) -> None:
        from . import models as _models  # noqa: F401
        from app.auth import rate_limit as _rate_limit  # noqa: F401
        Base.metadata.drop_all(self.engine)

    def dispose(self) -> None:
        if self._engine is not None:
            self._engine.dispose()


def backend_name(url: str) -> str:
    if url.startswith('postgresql'):
        return 'postgresql'
    if url.startswith('sqlite'):
        return 'sqlite'
    return url.split(':', 1)[0]
