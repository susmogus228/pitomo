"""Pydantic DTOs for the HTTP API."""
from decimal import Decimal
from datetime import datetime
from .types import PetType, ProductKind
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VariantResponse(BaseModel):
    id: int
    sku: str
    label: str
    price: str
    original_price: str | None = None
    discount_percent: int | None = None
    currency: Literal['KZT']
    stock: int


class ProductPhotoResponse(BaseModel):
    id: int
    url: str


class ProductResponse(BaseModel):
    id: int
    name: str
    pet_type: PetType
    brand: str
    category: Literal['food', 'accessory']
    product_kind: ProductKind | None = None
    description: str
    composition: str | None = None
    material: str | None = None
    image_url: str | None = None
    images: list[ProductPhotoResponse] = Field(default_factory=list)
    is_hit: bool = False
    rating_average: float | None = None
    rating_count: int = 0
    discount_percent: int | None = None
    discount_start_at: datetime | None = None
    discount_end_at: datetime | None = None
    variants: list[VariantResponse]


class ProductPage(BaseModel):
    items: list[ProductResponse]
    total: int
    page: int
    page_size: int


class ProductKindResponse(BaseModel):
    id: ProductKind
    name: str
    count: int


class VariantCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    sku: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=100)
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    stock: int = Field(ge=0, le=2147483647)


class VariantUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    sku: str | None = Field(default=None, min_length=1, max_length=100)
    label: str | None = Field(default=None, min_length=1, max_length=100)
    price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    stock: int | None = Field(default=None, ge=0, le=2147483647)


class ProductCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    name: str = Field(min_length=1, max_length=200)
    pet_type: PetType
    brand: str = Field(min_length=1, max_length=100)
    category: Literal['food', 'accessory']
    product_kind: ProductKind | None = None
    composition: str | None = Field(default=None, max_length=1000)
    material: str | None = Field(default=None, max_length=500)
    variants: list[VariantCreate] = Field(min_length=1)

    @field_validator('composition', 'material')
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class ProductUpdate(BaseModel):
    """Editable product fields.

    Category is intentionally absent: changing Food into Accessory would change
    the domain class, so v0.2 treats product category as immutable.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    name: str | None = Field(default=None, min_length=1, max_length=200)
    pet_type: PetType | None = None
    brand: str | None = Field(default=None, min_length=1, max_length=100)
    product_kind: ProductKind | None = None
    composition: str | None = Field(default=None, min_length=1, max_length=1000)
    material: str | None = Field(default=None, min_length=1, max_length=500)


class DiscountRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    percent: int = Field(ge=1, le=90)
    start_at: datetime | None = None
    end_at: datetime | None = None

    @field_validator('start_at', 'end_at')
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError('Укажите дату и время с часовым поясом')
        return value
