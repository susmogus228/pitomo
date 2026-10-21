"""Opaque revocable browser sessions with session-bound CSRF protection."""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from urllib.parse import urlsplit

from fastapi import Request, Response
from sqlalchemy import delete

from app.db.models import BrowserSessionORM
from app.users.repository import SQLAlchemyUserRepository
from .exceptions import AuthenticationRequiredError, AuthorizationError

SESSION_COOKIE = 'pitomo_session'
CSRF_COOKIE = 'pitomo_csrf'


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_token(token: str, secret: str) -> str:
    return hmac.new(secret.encode(), ('pitomo-csrf:' + token).encode(), hashlib.sha256).hexdigest()


def require_browser_origin(request: Request, settings) -> None:
    origin = request.headers.get('origin', '')
    try:
        parts = urlsplit(origin)
    except ValueError as exc:
        raise AuthorizationError('Недопустимый источник запроса') from exc
    if parts.scheme not in {'http', 'https'} or not parts.netloc or parts.path or parts.query or parts.fragment or parts.username:
        raise AuthorizationError('Недопустимый источник запроса')
    # The reverse proxy preserves Host. Production's public scheme is HTTPS;
    # forwarded headers from arbitrary clients are not used for this decision.
    scheme = 'https' if settings.environment == 'production' else request.url.scheme
    expected = f'{scheme}://{request.headers.get("host", "")}'
    if origin != expected and origin != settings.public_origin and origin not in settings.cors_origins:
        raise AuthorizationError('Недопустимый источник запроса')


def require_csrf(request: Request, settings, token: str) -> None:
    require_browser_origin(request, settings)
    supplied = request.headers.get('x-csrf-token', '')
    cookie = request.cookies.get(CSRF_COOKIE, '')
    expected = csrf_token(token, settings.jwt_secret)
    if not supplied.isascii() or not cookie.isascii() or not supplied or not hmac.compare_digest(supplied, cookie) or not hmac.compare_digest(supplied, expected):
        raise AuthorizationError('Проверка CSRF не пройдена. Обновите страницу.')


def browser_user(request: Request, session, settings):
    token = request.cookies.get(SESSION_COOKIE, '')
    if len(token) != 64 or not token.isascii():
        raise AuthenticationRequiredError('Требуется вход в аккаунт')
    row = session.get(BrowserSessionORM, token_hash(token))
    now = datetime.now(timezone.utc)
    expires_at = None if row is None else row.expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at is None or expires_at <= now:
        raise AuthenticationRequiredError('Сессия истекла. Войдите снова.')
    user = SQLAlchemyUserRepository(session).get(row.user_id)
    if user is None or not user.is_active:
        raise AuthenticationRequiredError('Требуется вход в аккаунт')
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        require_csrf(request, settings, token)
    return user


def start_session(request: Request, response: Response, session, settings, user_id: int) -> None:
    now = datetime.now(timezone.utc)
    session.execute(delete(BrowserSessionORM).where(BrowserSessionORM.expires_at <= now))
    previous = request.cookies.get(SESSION_COOKIE)
    if previous:
        session.execute(delete(BrowserSessionORM).where(BrowserSessionORM.token_hash == token_hash(previous)))
    token = secrets.token_hex(32)
    ttl = settings.access_token_minutes * 60
    session.add(BrowserSessionORM(token_hash=token_hash(token), user_id=user_id, expires_at=now + timedelta(seconds=ttl)))
    secure = settings.environment == 'production' or settings.secure_cookies
    response.set_cookie(SESSION_COOKIE, token, max_age=ttl, httponly=True, secure=secure, samesite='lax', path='/')
    response.set_cookie(CSRF_COOKIE, csrf_token(token, settings.jwt_secret), max_age=ttl, httponly=False, secure=secure, samesite='lax', path='/')


def end_session(request: Request, response: Response, session, settings) -> None:
    token = request.cookies.get(SESSION_COOKIE, '')
    session.execute(delete(BrowserSessionORM).where(BrowserSessionORM.token_hash == token_hash(token)))
    secure = settings.environment == 'production' or settings.secure_cookies
    response.delete_cookie(SESSION_COOKIE, path='/', httponly=True, secure=secure, samesite='lax')
    response.delete_cookie(CSRF_COOKIE, path='/', httponly=False, secure=secure, samesite='lax')
