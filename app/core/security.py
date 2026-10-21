"""Versioned password hashes and strict HS256 tokens backed by PyJWT."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

import jwt

PASSWORD_ITERATIONS = 600_000

class TokenError(ValueError):
    """Raised when a JWT cannot be trusted or has expired."""


def hash_password(password: str, *, iterations: int = PASSWORD_ITERATIONS) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256 and a random salt."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return 'pbkdf2_sha256${}${}${}'.format(
        iterations,
        _b64encode(salt),
        _b64encode(digest),
    )


def verify_password(password: str, encoded: str) -> bool:
    """Verify a plain password against the stored PBKDF2 representation."""
    try:
        scheme, iterations_raw, salt_raw, digest_raw = encoded.split('$', 3)
        if scheme != 'pbkdf2_sha256':
            return False
        iterations = int(iterations_raw)
        if not 1 <= iterations <= 2_000_000:
            return False
        salt = _b64decode(salt_raw)
        expected = _b64decode(digest_raw)
        if len(salt) != 16 or len(expected) != 32:
            return False
    except (ValueError, TypeError):
        return False

    actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return hmac.compare_digest(actual, expected)


def password_needs_rehash(encoded: str) -> bool:
    return int(encoded.split('$', 3)[1]) < PASSWORD_ITERATIONS


def create_access_token(
    *,
    subject: int,
    secret: str,
    expires_minutes: int,
) -> str:
    """Create a compact JWT signed with HS256."""
    now = int(time.time())
    payload = {
        'sub': str(subject),
        'iat': now,
        'exp': now + expires_minutes * 60,
    }
    return jwt.encode(payload, secret, algorithm='HS256', headers={'typ': 'JWT'})


def decode_access_token(token: str, *, secret: str) -> dict[str, Any]:
    """Validate signature/expiration and return the JWT payload."""
    try:
        for segment in token.split('.'):
            _b64decode(segment)
        payload = jwt.decode(token, secret, algorithms=['HS256'], options={'require': ['exp', 'iat', 'sub']})
        header = jwt.get_unverified_header(token)
        if header.get('typ') != 'JWT':
            raise ValueError('Invalid token type')
        if type(payload['exp']) is not int or type(payload['iat']) is not int:
            raise ValueError('Invalid numeric date')
        subject = payload['sub']
        if not isinstance(subject, str) or not subject.isascii() or not subject.isdecimal():
            raise ValueError('Invalid subject')
        if not 1 <= int(subject) <= 2_147_483_647 or str(int(subject)) != subject:
            raise ValueError('Invalid subject')
        if payload['exp'] <= payload['iat']:
            raise ValueError('Invalid expiration')
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise TokenError('Недействительный токен') from exc
    return payload


def _json_segment(value: dict[str, Any]) -> str:
    raw = json.dumps(value, separators=(',', ':'), sort_keys=True).encode('utf-8')
    return _b64encode(raw)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')


def _b64decode(value: str) -> bytes:
    """Decode canonical unpadded Base64URL.

    Python's permissive decoder accepts multiple textual encodings that can
    decode to the same bytes when only unused trailing bits differ. For JWTs
    that means a token string could be changed while still producing the same
    signature bytes. Re-encoding the decoded value and comparing it with the
    original rejects such non-canonical aliases.
    """
    if not isinstance(value, str) or not value or '=' in value:
        raise ValueError('Некорректный Base64URL')
    try:
        raw = value.encode('ascii')
    except UnicodeEncodeError as exc:
        raise ValueError('Некорректный Base64URL') from exc

    padding = b'=' * (-len(raw) % 4)
    decoded = base64.b64decode(raw + padding, altchars=b'-_', validate=True)
    if _b64encode(decoded) != value:
        raise ValueError('Неканоничный Base64URL')
    return decoded
