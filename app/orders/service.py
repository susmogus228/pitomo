"""Order use cases and checkout business rules."""
from __future__ import annotations

from threading import RLock
from datetime import datetime, timezone
import hashlib
import json

from app.cart.repository import CartRepository
from app.cart.repository import InMemoryCartRepository
from app.catalog.repository import InMemoryProductRepository
from .repository import InMemoryOrderRepository
from app.catalog.repository import ProductRepository

from .exceptions import EmptyCartError, InvalidOrderDataError, OrderCheckoutError, OrderNotFoundError
from .models import DELIVERY_STAGES, Order, OrderItem
from .schemas import DeliveryUpdateRequest
from .repository import OrderRepository


class OrderService:
    """Create immutable purchase snapshots from the authenticated user's cart.

    SQL repositories share the request transaction. The session dependency
    commits before response delivery; any error rolls back stock, cart and order
    together. Database row locks serialize owners and SKU stock across workers.
    The local lock supports sequential in-memory examples only.
    """

    def __init__(
        self,
        order_repository: OrderRepository,
        cart_repository: CartRepository,
        product_repository: ProductRepository,
    ):
        self.order_repository = order_repository
        self.cart_repository = cart_repository
        self.product_repository = product_repository
        self._checkout_lock = RLock()

    def checkout(self, user_id: int, *, idempotency_key: str | None = None, details=None,
                 demo_enabled: bool = False) -> dict:
        if idempotency_key is not None and (not idempotency_key or len(idempotency_key) > 128):
            raise InvalidOrderDataError('Idempotency-Key должен содержать от 1 до 128 символов')
        values = details.model_dump() if details is not None else {}
        fingerprint = hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False,
                                                default=str).encode()).hexdigest()
        with self._checkout_lock:
            self.cart_repository.lock_user(user_id)
            if idempotency_key is not None:
                previous = self.order_repository.get_by_key(user_id, idempotency_key)
                if previous is not None:
                    if previous.checkout_fingerprint and previous.checkout_fingerprint != fingerprint:
                        raise OrderCheckoutError('Idempotency-Key уже использован с другими данными заказа')
                    return self._serialize_order(previous)
            if values.get('payment_method') == 'demo' and not demo_enabled:
                raise OrderCheckoutError('Тестовая оплата недоступна')
            cart = self.cart_repository.get_by_user_id(user_id)
            if cart is None or not cart.items:
                raise EmptyCartError('Корзина пуста')
            snapshots = []
            stock_changes = []
            for item in sorted(cart.items, key=lambda item: item.variant_id):
                found = self.product_repository.find_variant(item.variant_id, for_update=True)
                if found is None:
                    raise OrderCheckoutError(f'Вариант товара {item.variant_id} больше недоступен в каталоге')
                product, variant = found
                if variant.stock < item.quantity:
                    raise OrderCheckoutError(f'Недостаточно товара для SKU {variant.sku}: доступно {variant.stock}, требуется {item.quantity}')
                snapshots.append(OrderItem(
                    product_id=product.id, product_name=product.name, variant_id=variant.id,
                    sku=variant.sku, variant_label=variant.label, unit_price=variant.price,
                    original_unit_price=variant.original_price,
                    quantity=item.quantity, currency=variant.currency,
                ))
                stock_changes.append((variant.id, variant.stock, item.quantity))
            order = Order(id=self.order_repository.next_order_id(), user_id=user_id, items=snapshots,
                **values, checkout_fingerprint=fingerprint,
                payment_status='pending' if values.get('payment_method') == 'demo' else 'cod_pending')
            if order.delivery_tracking is not None:
                order.delivery_tracking.record('created', occurred_at=order.created_at)
            # SQL adapters share one transaction. Never issue compensating writes
            # against a failed SQL session; the request owner performs rollback.
            memory = (isinstance(self.cart_repository, InMemoryCartRepository)
                      and isinstance(self.product_repository, InMemoryProductRepository)
                      and isinstance(self.order_repository, InMemoryOrderRepository))
            original_items = [(item.variant_id, item.quantity) for item in cart.items] if memory else []
            try:
                for variant_id, stock, quantity in stock_changes:
                    self.product_repository.set_variant_stock(variant_id, stock - quantity)
                if idempotency_key is None:
                    self.order_repository.add(order)
                else:
                    self.order_repository.add(order, idempotency_key=idempotency_key)
                cart.clear()
                self.cart_repository.save(cart)
            except Exception:
                if memory:
                    for variant_id, stock, _ in stock_changes:
                        self.product_repository.set_variant_stock(variant_id, stock)
                    self.order_repository.delete(order.id)
                    cart.clear()
                    for variant_id, quantity in original_items:
                        cart.add_item(variant_id, quantity)
                    self.cart_repository.save(cart)
                raise
            return self._serialize_order(order)

    def demo_payment(self, user_id: int, order_id: int, outcome: str, *, enabled: bool) -> dict:
        with self._checkout_lock:
            order = self._owned_locked_order(user_id, order_id)
            if not enabled or order.payment_method != 'demo':
                raise OrderCheckoutError('Тестовая оплата недоступна для этого заказа')
            if order.status == 'cancelled':
                raise OrderCheckoutError('Заказ отменён')
            if order.payment_status == 'demo_paid':
                return self._serialize_order(order)
            if outcome not in {'success', 'failure'}:
                raise InvalidOrderDataError('Неподдерживаемый результат тестовой оплаты')
            order.payment_status = 'demo_paid' if outcome == 'success' else 'failed'
            order.paid_at = datetime.now(timezone.utc) if outcome == 'success' else None
            self.order_repository.save_status(order)
            return self._serialize_order(order)

    def cancel(self, user_id: int, order_id: int) -> dict:
        with self._checkout_lock:
            order = self._owned_locked_order(user_id, order_id)
            if order.status == 'cancelled':
                return self._serialize_order(order)
            if order.received_at is not None:
                raise OrderCheckoutError('Полученный заказ нельзя отменить')
            if order.payment_status == 'demo_paid':
                raise OrderCheckoutError('Оплаченный тестовый заказ нельзя отменить: возвраты не реализованы')
            if order.delivery_tracking is not None and order.delivery_tracking.stage != 'warehouse':
                raise OrderCheckoutError('Отправленный заказ нельзя отменить: возврат доставки не реализован')
            changes = []
            for item in sorted(order.items, key=lambda item: item.variant_id):
                found = self.product_repository.find_variant(item.variant_id, for_update=True)
                if found is None:
                    continue  # Deleted SKUs stay deleted; their historical snapshots remain intact.
                _, variant = found
                stock = variant.stock + item.quantity
                if stock > 2147483647:
                    raise OrderCheckoutError('Отмена превысит допустимый остаток товара')
                changes.append((variant.id, stock))
            for variant_id, stock in changes:
                self.product_repository.set_variant_stock(variant_id, stock)
            order.status = 'cancelled'
            order.payment_status = 'cancelled'
            order.paid_at = None
            self.order_repository.save_status(order)
            return self._serialize_order(order)

    def confirm_receipt(self, user_id: int, order_id: int) -> dict:
        with self._checkout_lock:
            order = self._owned_locked_order(user_id, order_id)
            if order.received_at is not None:
                return self._serialize_order(order)
            if order.status == 'cancelled':
                raise OrderCheckoutError('Отменённый заказ нельзя подтвердить полученным')
            if order.payment_method == 'demo' and order.payment_status != 'demo_paid':
                raise OrderCheckoutError('Сначала завершите тестовую оплату')
            if order.payment_method == 'cod' and order.payment_status != 'cod_pending':
                raise OrderCheckoutError('Неподдерживаемый статус оплаты')
            tracking = order.delivery_tracking
            if tracking is not None and (tracking.stage != 'nearby' or tracking.incident is not None):
                raise OrderCheckoutError('Подтвердите получение, когда доставка будет рядом и без поломки')
            order.received_at = datetime.now(timezone.utc)
            self.order_repository.save_status(order)
            return self._serialize_order(order)

    def update_delivery(self, order_id: int, command: DeliveryUpdateRequest) -> dict:
        """Apply one admin command under the same row lock as payment/receipt/cancellation.

        A stale version always conflicts, including retries. A no-op carrying the
        current version returns the unchanged snapshot and creates no audit event.
        """
        with self._checkout_lock:
            order = self.order_repository.get_locked(order_id)
            if order is None:
                raise OrderNotFoundError('Заказ не найден')
            tracking = order.delivery_tracking
            if tracking is None:
                raise OrderCheckoutError('Для самовывоза отслеживание доставки недоступно')
            if order.status == 'cancelled' or order.received_at is not None:
                raise OrderCheckoutError('Доставка завершённого или отменённого заказа недоступна для изменения')
            if tracking.version != command.expected_version:
                raise OrderCheckoutError('Доставка уже обновлена. Обновите заказ и повторите действие')
            if 'stage' in command.model_fields_set:
                if command.stage == tracking.stage:
                    return self._serialize_order(order)
                if tracking.incident is not None:
                    raise OrderCheckoutError('Сначала устраните поломку доставки')
                current_index = DELIVERY_STAGES.index(tracking.stage)
                if current_index + 1 >= len(DELIVERY_STAGES) or command.stage != DELIVERY_STAGES[current_index + 1]:
                    raise OrderCheckoutError('Этапы доставки меняются только последовательно вперёд')
                if order.payment_method == 'demo' and order.payment_status != 'demo_paid':
                    raise OrderCheckoutError('Сначала завершите тестовую оплату')
                if order.payment_method == 'cod' and order.payment_status != 'cod_pending':
                    raise OrderCheckoutError('Неподдерживаемый статус оплаты')
                tracking.stage = command.stage
                event_type, note = 'stage_changed', None
            else:
                if command.incident == tracking.incident and command.incident_note == tracking.incident_note:
                    return self._serialize_order(order)
                if command.incident is None:
                    note = tracking.incident_note
                    event_type = 'incident_resolved'
                else:
                    note = command.incident_note
                    event_type = 'incident_reported'
                tracking.incident = command.incident
                tracking.incident_note = command.incident_note
            tracking.version += 1
            tracking.record(event_type, note=note)
            self.order_repository.save_delivery(order)
            return self._serialize_order(order)

    def _owned_locked_order(self, user_id: int, order_id: int) -> Order:
        # All cart/order writes share owner -> order -> ascending SKU lock order.
        self.cart_repository.lock_user(user_id)
        order = self.order_repository.get_locked(order_id)
        if order is None or order.user_id != user_id:
            raise OrderNotFoundError('Заказ не найден')
        return order

    def list_orders(self, user_id: int, *, limit: int = 50, offset: int = 0) -> list[dict]:
        return [self._serialize_order(order) for order in self.order_repository.all_for_user(user_id, limit=limit, offset=offset)]

    def get_order(self, user_id: int, order_id: int) -> dict:
        order = self.order_repository.get(order_id)
        if order is None or order.user_id != user_id:
            raise OrderNotFoundError('Заказ не найден')
        return self._serialize_order(order)

    @staticmethod
    def _serialize_order(order: Order) -> dict:
        return {
            'id': order.id,
            'user_id': order.user_id,
            'status': order.status,
            'created_at': order.created_at,
            'items': [
                {
                    'product_id': item.product_id,
                    'product_name': item.product_name,
                    'variant_id': item.variant_id,
                    'sku': item.sku,
                    'variant_label': item.variant_label,
                    'unit_price': str(item.unit_price),
                    'original_unit_price': str(item.original_unit_price) if item.original_unit_price is not None else None,
                    'currency': item.currency,
                    'quantity': item.quantity,
                    'line_total': str(item.line_total),
                }
                for item in order.items
            ],
            'total_items': order.total_items,
            'total': str(order.total),
            'currency': 'KZT',
            'contact_name': order.contact_name,
            'phone': order.phone,
            'delivery_method': order.delivery_method,
            'address': order.address,
            'delivery_lat': order.delivery_lat,
            'delivery_lon': order.delivery_lon,
            'received_at': order.received_at,
            'paid_at': order.paid_at,
            'comment': order.comment,
            'payment_method': order.payment_method,
            'payment_status': order.payment_status,
            'is_demo': order.payment_method == 'demo',
            'delivery_tracking': order.delivery_tracking.payload() if order.delivery_tracking else None,
        }
