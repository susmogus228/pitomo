"""FastAPI dependencies for authenticated and admin-only routes."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db.dependencies import SessionDependency
from app.users.models import User
from app.users.repository import SQLAlchemyUserRepository

from .exceptions import AuthenticationRequiredError, AuthorizationError
from .service import AuthService
from .browser import browser_user

bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_service(
    session: SessionDependency,
) -> AuthService:
    settings = session.info['settings']
    return AuthService(SQLAlchemyUserRepository(session), settings)


AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    service: AuthServiceDependency,
    session: SessionDependency,
) -> User:
    if credentials is not None and credentials.scheme.casefold() == 'bearer':
        user = service.user_from_token(credentials.credentials)
    elif request.headers.get('authorization'):
        raise AuthenticationRequiredError('Недействительный Bearer-токен')
    else:
        user = browser_user(request, session, service.settings)
    request.state.user_id = user.id
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(current_user: CurrentUser) -> User:
    if not current_user.is_admin:
        raise AuthorizationError('Требуются права администратора')
    return current_user


AdminUser = Annotated[User, Depends(require_admin)]
