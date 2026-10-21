"""Transport schemas for registration and authentication."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.privacy.schemas import ConsentInput


class RegistrationIdentity(BaseModel):
    model_config = ConfigDict(extra='forbid')

    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)

    @field_validator('email', 'first_name', 'last_name', mode='before')
    @classmethod
    def strip_profile_fields(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized.count('@') != 1:
            raise ValueError('Некорректный email')
        local, domain = normalized.split('@')
        if not local or '.' not in domain or domain.startswith('.') or domain.endswith('.'):
            raise ValueError('Некорректный email')
        return normalized


class UserRegister(RegistrationIdentity):
    consent: ConsentInput


class UserLogin(BaseModel):
    model_config = ConfigDict(extra='forbid')

    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator('email', mode='before')
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().casefold() if isinstance(value, str) else value


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    expires_in: int
