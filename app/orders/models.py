"""Domain entities for customer orders.

Orders intentionally store purchase snapshots instead of live references to
catalog prices/names. This makes historical orders stable when catalog data is
edited after checkout.
"""
from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass
from decimal import Decimal


DELIVERY_STAGES = ('warehouse', 'in_transit', 'nearby')
DELIVERY_INCIDENTS = ('flat_tire', 'overturned', 'engine_failure')


@dataclass
class DeliveryTracking:
    """Current delivery state and append-only public event snapshots."""

    stage: str = 'warehouse'
    incident: str | None = None
    incident_note: str | None = None
    updated_at: datetime | None = None
    version: int = 0
    history: list[dict] | None = None

    def __post_init__(self):
        if self.stage not in DELIVERY_STAGES or self.incident not in (None, *DELIVERY_INCIDENTS):
            raise ValueError('Неподдерживаемое состояние доставки')
        if type(self.version) is not int or self.version < 0:
            raise ValueError('Версия доставки должна быть неотрицательным целым числом')
        self.history = [dict(event) for event in (self.history or [])]
        for event in self.history:
            if isinstance(event['occurred_at'], str):
                event['occurred_at'] = datetime.fromisoformat(event['occurred_at'])
        if self.updated_at is not None and self.updated_at.tzinfo is None:
            self.updated_at = self.updated_at.replace(tzinfo=timezone.utc)

    def record(self, event_type: str, *, occurred_at: datetime | None = None,
               note: str | None = None) -> None:
        self.updated_at = occurred_at or datetime.now(timezone.utc)
        self.history.append({'event_type': event_type, 'stage': self.stage,
                             'incident': self.incident, 'note': note,
                             'occurred_at': self.updated_at})

    def storage_history(self) -> list[dict]:
        # Replace JSON values on every save; do not rely on in-place JSON mutation tracking.
        return [{**event, 'occurred_at': event['occurred_at'].isoformat()}
                for event in self.history]

    def payload(self) -> dict:
        return {'stage': self.stage, 'incident': self.incident,
                'incident_note': self.incident_note, 'updated_at': self.updated_at,
                'version': self.version, 'history': [dict(event) for event in self.history]}


@dataclass(frozen=True, init=False)
class OrderItem:
    """Immutable-at-purchase snapshot of one cart line."""

    product_id: int
    product_name: str
    variant_id: int
    sku: str
    variant_label: str
    unit_price: Decimal
    original_unit_price: Decimal | None
    quantity: int
    currency: str

    def __init__(
        self,
        *,
        product_id: int,
        product_name: str,
        variant_id: int,
        sku: str,
        variant_label: str,
        unit_price: str | Decimal,
        quantity: int,
        currency: str = 'KZT',
        original_unit_price: str | Decimal | None = None,
    ):
        if type(product_id) is not int or not 1 <= product_id <= 2147483647:
            raise ValueError('product_id должен быть положительным целым числом')
        if type(variant_id) is not int or not 1 <= variant_id <= 2147483647:
            raise ValueError('variant_id должен быть положительным целым числом')
        if type(quantity) is not int or not 1 <= quantity <= 10000:
            raise ValueError('Количество должно быть положительным целым числом')
        if currency != 'KZT':
            raise ValueError('Поддерживается только валюта KZT')

        object.__setattr__(self, 'product_id', product_id)
        object.__setattr__(self, 'product_name', self._required_text(product_name, 'Название товара'))
        object.__setattr__(self, 'variant_id', variant_id)
        object.__setattr__(self, 'sku', self._required_text(sku, 'SKU'))
        object.__setattr__(self, 'variant_label', self._required_text(variant_label, 'Название варианта'))
        price = Decimal(str(unit_price))
        if not price.is_finite() or not 0 <= price <= Decimal("9999999999.99") or price != price.quantize(Decimal('0.01')):
            raise ValueError('Цена должна быть неотрицательной с максимум 2 знаками после запятой')
        object.__setattr__(self, 'unit_price', price.quantize(Decimal('0.01')))
        original = Decimal(str(original_unit_price)) if original_unit_price is not None else None
        if original is not None and (not original.is_finite() or original < price or
                                    original > Decimal('9999999999.99') or
                                    original != original.quantize(Decimal('0.01'))):
            raise ValueError('Исходная цена должна быть не меньше цены продажи')
        object.__setattr__(self, 'original_unit_price', original)
        object.__setattr__(self, 'quantity', quantity)
        object.__setattr__(self, 'currency', currency)

    @staticmethod
    def _required_text(value: str, field_name: str) -> str:
        if value is None:
            raise ValueError(f'{field_name} не может быть пустым')
        value = str(value).strip()
        if not value:
            raise ValueError(f'{field_name} не может быть пустым')
        return value

    @property
    def line_total(self) -> Decimal:
        return (self.unit_price * self.quantity).quantize(Decimal('0.01'))


class Order:
    """A completed checkout owned by one user."""

    def __init__(
        self,
        *,
        id: int,
        user_id: int,
        items: list[OrderItem] | tuple[OrderItem, ...],
        created_at: datetime | None = None,
        status: str = 'created',
        contact_name: str | None = None,
        phone: str | None = None,
        delivery_method: str = 'pickup',
        address: str | None = None,
        comment: str | None = None,
        payment_method: str = 'cod',
        payment_status: str = 'cod_pending',
        checkout_fingerprint: str | None = None,
        paid_at: datetime | None = None,
        received_at: datetime | None = None,
        delivery_lat: str | Decimal | None = None,
        delivery_lon: str | Decimal | None = None,
        delivery_tracking: DeliveryTracking | None = None,
    ):
        if type(id) is not int or not 1 <= id <= 2147483647:
            raise ValueError('id заказа должен быть положительным целым числом')
        if type(user_id) is not int or not 1 <= user_id <= 2147483647:
            raise ValueError('user_id должен быть положительным целым числом')
        if not items:
            raise ValueError('Заказ не может быть пустым')
        if status not in {'created', 'cancelled'}:
            raise ValueError('Неподдерживаемый статус заказа')
        if delivery_method not in {'pickup', 'delivery'} or payment_method not in {'demo', 'cod'}:
            raise ValueError('Неподдерживаемый способ доставки или оплаты')
        if payment_status not in {'pending', 'demo_paid', 'failed', 'cod_pending', 'cancelled'}:
            raise ValueError('Неподдерживаемый статус оплаты')

        self.id = id
        self.user_id = user_id
        self.__items = tuple(items)
        self.status = status
        self.contact_name = contact_name
        self.phone = phone
        self.delivery_method = delivery_method
        self.address = address
        self.comment = comment
        self.payment_method = payment_method
        self.payment_status = payment_status
        self.checkout_fingerprint = checkout_fingerprint
        self.paid_at = paid_at
        if self.paid_at is not None and self.paid_at.tzinfo is None:
            self.paid_at = self.paid_at.replace(tzinfo=timezone.utc)
        self.received_at = received_at
        if self.received_at is not None and self.received_at.tzinfo is None:
            self.received_at = self.received_at.replace(tzinfo=timezone.utc)
        self.delivery_lat = Decimal(str(delivery_lat)) if delivery_lat is not None else None
        self.delivery_lon = Decimal(str(delivery_lon)) if delivery_lon is not None else None
        if (self.delivery_lat is None) != (self.delivery_lon is None):
            raise ValueError('Координаты доставки указываются парой')
        self.created_at = created_at or datetime.now(timezone.utc)
        if self.created_at.tzinfo is None:
            self.created_at = self.created_at.replace(tzinfo=timezone.utc)
        self.created_at = self.created_at.astimezone(timezone.utc)
        self.delivery_tracking = (delivery_tracking or DeliveryTracking(
            stage='nearby' if self.received_at is not None else 'warehouse'
        )) if delivery_method == 'delivery' else None

    @property
    def items(self) -> tuple[OrderItem, ...]:
        return self.__items

    @property
    def total_items(self) -> int:
        return sum(item.quantity for item in self.__items)

    @property
    def total(self) -> Decimal:
        return sum((item.line_total for item in self.__items), Decimal('0.00')).quantize(Decimal('0.01'))
