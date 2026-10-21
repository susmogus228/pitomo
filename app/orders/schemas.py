"""Pydantic transport schemas for the orders API."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    contact_name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=7, max_length=32, pattern=r'^\+?[0-9 ()-]+$')
    delivery_method: Literal['pickup', 'delivery'] = 'pickup'
    address: str | None = Field(default=None, max_length=500)
    delivery_lat: Decimal | None = Field(default=None, ge=-90, le=90, max_digits=10, decimal_places=7)
    delivery_lon: Decimal | None = Field(default=None, ge=-180, le=180, max_digits=10, decimal_places=7)
    comment: str | None = Field(default=None, max_length=1000)
    payment_method: Literal['demo', 'cod'] = 'cod'

    @model_validator(mode='after')
    def validate_delivery(self):
        if len(''.join(c for c in self.phone if c.isdigit())) < 7:
            raise ValueError('Укажите корректный номер телефона')
        if self.delivery_method == 'delivery' and (not self.address or len(self.address) < 5):
            raise ValueError('Для доставки требуется адрес')
        if (self.delivery_lat is None) != (self.delivery_lon is None):
            raise ValueError('Координаты доставки указываются парой')
        if self.delivery_method != 'delivery' and self.delivery_lat is not None:
            raise ValueError('Координаты допустимы только для доставки')
        return self


class DemoPaymentRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    outcome: Literal['success', 'failure']


class OrderItemResponse(BaseModel):
    product_id: int
    product_name: str
    variant_id: int
    sku: str
    variant_label: str
    unit_price: str
    original_unit_price: str | None = None
    currency: Literal['KZT']
    quantity: int
    line_total: str


DeliveryStage = Literal['warehouse', 'in_transit', 'nearby']
DeliveryIncident = Literal['flat_tire', 'overturned', 'engine_failure']


class DeliveryEventResponse(BaseModel):
    event_type: Literal['created', 'stage_changed', 'incident_reported', 'incident_resolved']
    stage: DeliveryStage
    incident: DeliveryIncident | None
    note: str | None
    occurred_at: datetime


class DeliveryTrackingResponse(BaseModel):
    stage: DeliveryStage
    incident: DeliveryIncident | None
    incident_note: str | None
    updated_at: datetime | None
    version: int
    history: list[DeliveryEventResponse]


class DeliveryUpdateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    expected_version: int = Field(strict=True, ge=0, le=2147483647)
    stage: DeliveryStage | None = None
    incident: DeliveryIncident | None = None
    incident_note: str | None = Field(default=None, max_length=500)

    @model_validator(mode='after')
    def validate_command(self):
        stage_supplied = 'stage' in self.model_fields_set
        incident_supplied = 'incident' in self.model_fields_set
        if stage_supplied == incident_supplied:
            raise ValueError('Передайте ровно одно действие: stage или incident')
        if stage_supplied and self.stage is None:
            raise ValueError('Этап доставки не может быть null')
        if 'incident_note' in self.model_fields_set and (not incident_supplied or self.incident is None):
            raise ValueError('Примечание допустимо только при сообщении о поломке')
        self.incident_note = self.incident_note or None
        return self


class OrderResponse(BaseModel):
    id: int
    user_id: int
    status: Literal['created', 'cancelled']
    created_at: datetime
    items: list[OrderItemResponse]
    total_items: int
    total: str
    currency: Literal['KZT']
    contact_name: str | None = None
    phone: str | None = None
    delivery_method: Literal['pickup', 'delivery'] = 'pickup'
    address: str | None = None
    delivery_lat: Decimal | None = None
    delivery_lon: Decimal | None = None
    received_at: datetime | None = None
    paid_at: datetime | None = None
    comment: str | None = None
    payment_method: Literal['demo', 'cod'] = 'cod'
    payment_status: Literal['pending', 'demo_paid', 'failed', 'cod_pending', 'cancelled'] = 'cod_pending'
    is_demo: bool = False
    delivery_tracking: DeliveryTrackingResponse | None = None
