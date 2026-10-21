"""Shared database-backed authentication attempt limits."""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import time

from sqlalchemy import Float, Integer, String, case, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Mapped, mapped_column
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from app.db.base import Base


class LoginAttemptORM(Base):
    __tablename__ = 'login_attempts'
    key: Mapped[str] = mapped_column(String(96), primary_key=True)
    window_started: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)


def consume_attempt(database, settings, *, address: str, email: str, action: str) -> int:
    """Commit counters independently so failed logins cannot roll them back."""
    now = time.time()
    window = settings.login_window_seconds
    table = LoginAttemptORM.__table__
    def key(kind, value):
        digest = hmac.new(settings.jwt_secret.encode(), value.encode(), hashlib.sha256).hexdigest()
        return f'{kind}:{action}:{digest}'
    buckets = [(key('ip', address), settings.login_max_attempts * 10)]
    if email:
        buckets.append((key('account', email.strip().casefold()), settings.login_max_attempts))
    retry = 0
    with database.engine.begin() as connection:
        connection.execute(delete(table).where(table.c.window_started < now - window * 2))
        insert = pg_insert if connection.dialect.name == 'postgresql' else sqlite_insert
        for bucket, limit in sorted(buckets):
            expired = table.c.window_started <= now - window
            statement = insert(table).values(key=bucket, window_started=now, attempts=1)
            statement = statement.on_conflict_do_update(
                index_elements=[table.c.key],
                set_={
                    'window_started': case((expired, now), else_=table.c.window_started),
                    'attempts': case((expired, 1), (table.c.attempts >= limit + 1, limit + 1), else_=table.c.attempts + 1),
                },
            ).returning(table.c.attempts, table.c.window_started)
            count, started = connection.execute(statement).one()
            if count > limit:
                retry = max(retry, max(1, math.ceil(started + window - now)))
    return retry


class AuthLimitMiddleware:
    """Consume bounded auth bodies before opening the API transaction."""
    def __init__(self, app, *, database, settings):
        self.app, self.database, self.settings = app, database, settings

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        try:
            self.settings.validate()
        except ValueError:
            return await JSONResponse({'detail': 'Application configuration is invalid'}, status_code=503)(scope, receive, send)
        path = scope['path'].rstrip('/')
        if scope['method'] != 'POST' or path not in {'/api/v1/auth/login', '/api/v1/auth/register', '/api/v1/auth/browser/login'}:
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body', b'')
            size += len(chunk)
            if size > 16384:
                return await JSONResponse({'detail': 'Request body too large'}, status_code=413)(scope, receive, send)
            chunks.append(chunk)
            if not message.get('more_body', False):
                break
        body = b''.join(chunks)
        try:
            data = json.loads(body)
            email = data.get('email', '') if isinstance(data, dict) else ''
            email = email if isinstance(email, str) and len(email) <= 254 else ''
        except (ValueError, UnicodeError):
            email = ''
        address = (scope.get('client') or ('unknown', 0))[0]
        try:
            retry = await run_in_threadpool(consume_attempt, self.database, self.settings,
                                             address=address, email=email, action=path.rsplit('/', 1)[1])
        except Exception:
            return await JSONResponse({'detail': 'Authentication storage is unavailable'}, status_code=503)(scope, receive, send)
        if retry:
            return await JSONResponse({'detail': 'Слишком много попыток. Повторите позже.'}, status_code=429,
                                      headers={'Retry-After': str(retry)})(scope, receive, send)
        consumed = False
        async def replay():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {'type': 'http.request', 'body': body, 'more_body': False}
            return await receive()
        await self.app(scope, replay, send)
