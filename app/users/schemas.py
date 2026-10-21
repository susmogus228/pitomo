"""Pydantic transport schemas for user profiles."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    email: str | None = Field(default=None, min_length=5, max_length=254)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().casefold()
        if normalized.count('@') != 1:
            raise ValueError('Некорректный email')
        local, domain = normalized.split('@')
        if not local or '.' not in domain or domain.startswith('.') or domain.endswith('.'):
            raise ValueError('Некорректный email')
        return normalized


class UserResponse(BaseModel):
    id: int
    email: str
    first_name: str
    last_name: str | None
    is_active: bool
    role: str
