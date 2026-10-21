"""Pydantic transport schemas for the shopping cart API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CartItemCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    variant_id: int = Field(gt=0, le=2147483647)
    quantity: int = Field(gt=0, le=10000)


class CartItemUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    quantity: int = Field(gt=0, le=10000)


class CartItemResponse(BaseModel):
    product_id: int
    product_name: str
    image_url: str | None = None
    variant_id: int
    sku: str
    label: str
    unit_price: str
    original_unit_price: str | None = None
    currency: Literal['KZT']
    quantity: int
    available_stock: int
    is_available: bool
    line_total: str


class CartResponse(BaseModel):
    user_id: int
    items: list[CartItemResponse]
    total_items: int
    subtotal: str
    currency: Literal['KZT']
    can_checkout: bool


class CartOperationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    operation_key: str = Field(min_length=8, max_length=128, pattern=r'^[A-Za-z0-9_-]+$')
    expected_user_id: int | None = Field(default=None, strict=True, gt=0, le=2147483647)


class CartMergeItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    variant_id: int = Field(strict=True, gt=0, le=2147483647)
    quantity: int = Field(strict=True, gt=0, le=10000)


class CartRestoreRequest(CartOperationRequest, CartMergeItem):
    pass


class CartMergeRequest(CartOperationRequest):
    items: list[CartMergeItem] = Field(min_length=1, max_length=200)

    @model_validator(mode='after')
    def unique_items(self):
        if len({item.variant_id for item in self.items}) != len(self.items):
            raise ValueError('Каждый вариант указывается один раз')
        return self


class CartAdditionResult(BaseModel):
    variant_id: int
    requested_quantity: int
    added_quantity: int
    remaining_quantity: int
    status: Literal['added', 'reduced', 'out_of_stock', 'missing']
    message: str


class CartMutationResponse(BaseModel):
    cart: CartResponse
    items: list[CartAdditionResult]
    replayed: bool = False


class CartFavoriteResponse(BaseModel):
    cart: CartResponse
    product_id: int
    replayed: bool = False
