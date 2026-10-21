"""Transport schemas for administration endpoints."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator
from app.orders.schemas import OrderResponse
from app.users.schemas import UserResponse


class AdminOrderResponse(OrderResponse):
    customer_email: str
    customer_first_name: str


class AdminOrderPage(BaseModel):
    items: list[AdminOrderResponse]
    total: int
    limit: int
    offset: int


class AdminUserPage(BaseModel):
    items: list[UserResponse]
    total: int
    limit: int
    offset: int


class AdminUserUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    role: Literal['customer', 'admin'] | None = None
    is_active: bool | None = None

    @model_validator(mode='after')
    def require_real_change(self):
        supplied = self.model_fields_set
        if not supplied:
            raise ValueError('Нужно передать role и/или is_active')
        if ('role' in supplied and self.role is None) or ('is_active' in supplied and self.is_active is None):
            raise ValueError('role и is_active не могут быть null')
        return self
