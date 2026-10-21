"""FastAPI dependency exposing one SQLAlchemy transaction per request."""
from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session


def get_db_session(request: Request) -> Generator[Session, None, None]:
    session = request.app.state.database.session_factory()
    session.info['settings'] = request.app.state.settings
    try:
        yield session
        session.commit()
        for path in session.info.get('deleted_uploads', ()):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass  # A cleanup retry can remove an orphan; the DB commit succeeded.
    except Exception:
        session.rollback()
        for path in session.info.get('created_uploads', ()):
            path.unlink(missing_ok=True)
        raise
    finally:
        session.close()


SessionDependency = Annotated[Session, Depends(get_db_session, scope='function')]
