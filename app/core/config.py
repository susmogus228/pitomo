"""Explicit runtime configuration and isolated test configuration."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

DEFAULT_POSTGRES_URL = 'postgresql+psycopg://petshop@127.0.0.1:5432/petshop'
TEST_DATABASE_URL = 'sqlite+pysqlite:///:memory:'
DEFAULT_REVIEW_UPLOAD_DIR = str(Path(__file__).resolve().parents[2] / 'uploads' / 'reviews') if os.name == 'nt' else '/app/uploads/reviews'


@dataclass(frozen=True)
class Settings:
    app_name: str = 'Petshop API'
    app_version: str = '0.14.0'
    environment: str = 'development'
    jwt_algorithm: str = 'HS256'
    jwt_secret: str = ''
    access_token_minutes: int = 30
    database_url: str = DEFAULT_POSTGRES_URL
    sql_echo: bool = False
    cors_origins: tuple[str, ...] = ()
    docs_enabled: bool = True
    login_max_attempts: int = 5
    login_window_seconds: int = 300
    demo_payments: bool | None = None
    public_origin: str | None = None
    secure_cookies: bool = False
    review_upload_dir: str = DEFAULT_REVIEW_UPLOAD_DIR
    geoapify_api_key: str = field(default='', repr=False)
    geoapify_daily_limit: int = 2800
    privacy_operator_name: str = ''
    privacy_operator_id: str = ''
    privacy_contact_email: str = ''
    privacy_storage_country: str = ''
    privacy_documents_approved: bool = False

    @property
    def demo_payments_enabled(self) -> bool:
        return self.environment in {'development', 'test'} and self.demo_payments is not False

    def validate(self) -> None:
        if self.environment not in {'development', 'test', 'production'}:
            raise ValueError('PETSHOP_ENV must be development, test or production')
        placeholders = ('change-me', 'changeme', 'replace', 'your-secret', 'dev-only')
        if len(self.jwt_secret.encode('utf-8')) < 32 or any(p in self.jwt_secret.lower() for p in placeholders):
            raise ValueError('PETSHOP_JWT_SECRET must contain a generated secret of at least 32 bytes')
        if self.jwt_algorithm != 'HS256':
            raise ValueError('Only HS256 is supported')
        if not 1 <= self.access_token_minutes <= 1440:
            raise ValueError('PETSHOP_ACCESS_TOKEN_MINUTES must be between 1 and 1440')
        if not 1 <= self.login_max_attempts <= 10000 or not 1 <= self.login_window_seconds <= 86400:
            raise ValueError('Login rate limit settings are outside supported bounds')
        if not self.database_url.startswith(('postgresql+psycopg://', 'sqlite+pysqlite://')):
            raise ValueError('Unsupported PETSHOP_DATABASE_URL')
        if self.environment == 'production' and self.demo_payments:
            raise ValueError('Demo payments must be disabled in production')
        if self.environment == 'production' and self.sql_echo:
            raise ValueError('SQL echo must be disabled in production')
        for origin in self.cors_origins:
            parts = urlsplit(origin)
            if parts.scheme not in {'http', 'https'} or not parts.netloc or parts.path or parts.query or parts.fragment or parts.username:
                raise ValueError('PETSHOP_CORS_ORIGINS must contain explicit HTTP origins')
        if self.public_origin:
            parts = urlsplit(self.public_origin)
            if parts.scheme != 'https' or not parts.netloc or parts.path or parts.query or parts.fragment or parts.username:
                raise ValueError('PETSHOP_PUBLIC_ORIGIN must be an explicit HTTPS origin')
        if not self.review_upload_dir or not os.path.isabs(self.review_upload_dir):
            raise ValueError('PETSHOP_REVIEW_UPLOAD_DIR must be an absolute path')
        if len(self.geoapify_api_key) > 256 or any(
            not char.isascii() or char.isspace() or ord(char) < 33
            for char in self.geoapify_api_key
        ):
            raise ValueError('PETSHOP_GEOAPIFY_API_KEY must be a valid API key')
        if not 1 <= self.geoapify_daily_limit <= 3000:
            raise ValueError('PETSHOP_GEOAPIFY_DAILY_LIMIT must be between 1 and 3000')

    @classmethod
    def for_testing(cls, **overrides) -> Settings:
        values = dict(environment='test', jwt_secret=secrets.token_urlsafe(48),
                      database_url=TEST_DATABASE_URL, login_max_attempts=1000)
        values.update(overrides)
        settings = cls(**values)
        settings.validate()
        return settings


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().casefold()
    if value not in {'1', 'true', 'yes', 'on', '0', 'false', 'no', 'off'}:
        raise ValueError(f'{name} must be a boolean')
    return value in {'1', 'true', 'yes', 'on'}


def load_settings() -> Settings:
    load_dotenv()
    environment = os.getenv('PETSHOP_ENV', 'development')
    return Settings(
        environment=environment,
        demo_payments=_env_bool('PETSHOP_DEMO_PAYMENTS', environment != 'production'),
        jwt_secret=os.getenv('PETSHOP_JWT_SECRET', ''),
        access_token_minutes=int(os.getenv('PETSHOP_ACCESS_TOKEN_MINUTES', '30')),
        database_url=os.getenv('PETSHOP_DATABASE_URL', DEFAULT_POSTGRES_URL),
        sql_echo=_env_bool('PETSHOP_SQL_ECHO'),
        docs_enabled=_env_bool('PETSHOP_DOCS_ENABLED', environment != 'production'),
        cors_origins=tuple(s.strip() for s in os.getenv('PETSHOP_CORS_ORIGINS', '').split(',') if s.strip()),
        login_max_attempts=int(os.getenv('PETSHOP_LOGIN_MAX_ATTEMPTS', '5')),
        login_window_seconds=int(os.getenv('PETSHOP_LOGIN_WINDOW_SECONDS', '300')),
        public_origin=os.getenv('PETSHOP_PUBLIC_ORIGIN', '').strip() or None,
        secure_cookies=_env_bool('PETSHOP_SECURE_COOKIES'),
        review_upload_dir=os.getenv('PETSHOP_REVIEW_UPLOAD_DIR', DEFAULT_REVIEW_UPLOAD_DIR),
        geoapify_api_key=os.getenv('PETSHOP_GEOAPIFY_API_KEY', '').strip(),
        geoapify_daily_limit=int(os.getenv('PETSHOP_GEOAPIFY_DAILY_LIMIT', '2800')),
        privacy_operator_name=os.getenv('PETSHOP_PRIVACY_OPERATOR_NAME', '').strip(),
        privacy_operator_id=os.getenv('PETSHOP_PRIVACY_OPERATOR_ID', '').strip(),
        privacy_contact_email=os.getenv('PETSHOP_PRIVACY_CONTACT_EMAIL', '').strip(),
        privacy_storage_country=os.getenv('PETSHOP_PRIVACY_STORAGE_COUNTRY', '').strip().upper(),
        privacy_documents_approved=_env_bool('PETSHOP_PRIVACY_DOCUMENTS_APPROVED'),
    )
