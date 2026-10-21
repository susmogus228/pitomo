"""Repository abstraction and SQLAlchemy implementation for orders."""
from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.mappers import order_to_domain
from app.db.models import OrderItemORM, OrderORM
from app.db.identifiers import next_id
from app.db.errors import unique_violation
from .exceptions import OrderCheckoutError

from .models import Order


class OrderRepository(ABC):
    def get_locked(self, order_id: int) -> Order | None:
        return self.get(order_id)

    def save_status(self, order: Order) -> None:
        raise NotImplementedError

    def save_delivery(self, order: Order) -> None:
        raise NotImplementedError

    def get_by_key(self, user_id: int, key: str) -> Order | None:
        return None

    @abstractmethod
    def get(self, order_id: int) -> Order | None:
        raise NotImplementedError

    @abstractmethod
    def all_for_user(self, user_id: int, *, limit: int = 50, offset: int = 0) -> tuple[Order, ...]:
        raise NotImplementedError

    @abstractmethod
    def add(self, order: Order, *, idempotency_key: str | None = None) -> Order:
        raise NotImplementedError

    @abstractmethod
    def delete(self, order_id: int) -> Order | None:
        raise NotImplementedError

    @abstractmethod
    def next_order_id(self) -> int:
        raise NotImplementedError


class InMemoryOrderRepository(OrderRepository):
    def save_delivery(self, order: Order) -> None:
        self.__orders[order.id] = order

    def save_status(self, order: Order) -> None:
        self.__orders[order.id] = order

    def __init__(self, orders: list[Order] | tuple[Order, ...] = ()):
        self.__orders = {order.id: order for order in orders}
        self.__keys = {}
        self.__next_order_id = max(self.__orders, default=0) + 1

    def get_by_key(self, user_id: int, key: str) -> Order | None:
        order_id = self.__keys.get((user_id, key))
        return self.__orders.get(order_id)

    def get(self, order_id: int) -> Order | None:
        return self.__orders.get(order_id)

    def all_for_user(self, user_id: int, *, limit: int = 50, offset: int = 0) -> tuple[Order, ...]:
        orders = [order for order in self.__orders.values() if order.user_id == user_id]
        orders.sort(key=lambda order: (order.created_at, order.id), reverse=True)
        return tuple(orders[offset:offset + min(limit, 100)])

    def add(self, order: Order, *, idempotency_key: str | None = None) -> Order:
        if order.id in self.__orders:
            raise ValueError('Р—Р°РєР°Р· СЃ С‚Р°РєРёРј ID СѓР¶Рµ СЃСѓС‰РµСЃС‚РІСѓРµС‚')
        self.__orders[order.id] = order
        if idempotency_key is not None:
            self.__keys[(order.user_id, idempotency_key)] = order.id
        return order

    def delete(self, order_id: int) -> Order | None:
        return self.__orders.pop(order_id, None)

    def next_order_id(self) -> int:
        value = self.__next_order_id
        self.__next_order_id += 1
        return value


class SQLAlchemyOrderRepository(OrderRepository):
    def __init__(self, session: Session):
        self.session = session

    def get_locked(self, order_id: int) -> Order | None:
        row = self.session.scalar(select(OrderORM).where(OrderORM.id == order_id)
            .with_for_update().execution_options(populate_existing=True))
        return order_to_domain(row) if row is not None else None

    def save_status(self, order: Order) -> None:
        from sqlalchemy import update
        self.session.execute(update(OrderORM).where(OrderORM.id == order.id).values(
            status=order.status, payment_status=order.payment_status,
            paid_at=order.paid_at, received_at=order.received_at))
        self.session.flush()

    def save_delivery(self, order: Order) -> None:
        from sqlalchemy import update
        tracking = order.delivery_tracking
        self.session.execute(update(OrderORM).where(OrderORM.id == order.id).values(
            delivery_stage=tracking.stage, delivery_incident=tracking.incident,
            delivery_incident_note=tracking.incident_note,
            delivery_updated_at=tracking.updated_at, delivery_version=tracking.version,
            delivery_history=tracking.storage_history()))
        self.session.flush()

    def get_by_key(self, user_id: int, key: str) -> Order | None:
        row = self.session.scalar(select(OrderORM).where(
            OrderORM.user_id == user_id, OrderORM.idempotency_key == key,
        ).options(selectinload(OrderORM.items)))
        return order_to_domain(row) if row is not None else None

    def get(self, order_id: int) -> Order | None:
        row = self.session.scalar(
            select(OrderORM)
            .where(OrderORM.id == order_id)
            .options(selectinload(OrderORM.items))
        )
        return order_to_domain(row) if row is not None else None

    def all_for_user(self, user_id: int, *, limit: int = 50, offset: int = 0) -> tuple[Order, ...]:
        rows = self.session.scalars(
            select(OrderORM)
            .where(OrderORM.user_id == user_id)
            .options(selectinload(OrderORM.items))
            .order_by(OrderORM.created_at.desc(), OrderORM.id.desc()).limit(min(limit, 100)).offset(offset)
        ).all()
        return tuple(order_to_domain(row) for row in rows)

    def add(self, order: Order, *, idempotency_key: str | None = None) -> Order:
        if self.session.get(OrderORM, order.id) is not None:
            raise ValueError('Р—Р°РєР°Р· СЃ С‚Р°РєРёРј ID СѓР¶Рµ СЃСѓС‰РµСЃС‚РІСѓРµС‚')
        row = OrderORM(
            id=order.id,
            user_id=order.user_id,
            status=order.status,
            created_at=order.created_at,
            contact_name=order.contact_name,
            phone=order.phone,
            delivery_method=order.delivery_method,
            address=order.address,
            comment=order.comment,
            payment_method=order.payment_method,
            payment_status=order.payment_status,
            paid_at=order.paid_at,
            received_at=order.received_at,
            delivery_lat=order.delivery_lat,
            delivery_lon=order.delivery_lon,
            checkout_fingerprint=order.checkout_fingerprint,
            delivery_stage=order.delivery_tracking.stage if order.delivery_tracking else None,
            delivery_incident=order.delivery_tracking.incident if order.delivery_tracking else None,
            delivery_incident_note=order.delivery_tracking.incident_note if order.delivery_tracking else None,
            delivery_updated_at=order.delivery_tracking.updated_at if order.delivery_tracking else None,
            delivery_version=order.delivery_tracking.version if order.delivery_tracking else 0,
            delivery_history=order.delivery_tracking.storage_history() if order.delivery_tracking else [],

            idempotency_key=idempotency_key,
        )
        row.items = [
            OrderItemORM(
                product_id=item.product_id,
                product_name=item.product_name,
                variant_id=item.variant_id,
                sku=item.sku,
                variant_label=item.variant_label,
                unit_price=item.unit_price,
                original_unit_price=item.original_unit_price,
                currency=item.currency,
                quantity=item.quantity,
            )
            for item in order.items
        ]
        self.session.add(row)
        try:
            self.session.flush()
        except IntegrityError as exc:
            if unique_violation(exc, names={'uq_orders_user_idempotency_key'},
                                sqlite_columns={'orders.user_id, orders.idempotency_key'}):
                raise OrderCheckoutError('Idempotency-Key СѓР¶Рµ РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ РґР»СЏ СЌС‚РѕРіРѕ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ') from exc
            raise
        return order

    def delete(self, order_id: int) -> Order | None:
        row = self.session.scalar(
            select(OrderORM)
            .where(OrderORM.id == order_id)
            .options(selectinload(OrderORM.items))
        )
        if row is None:
            return None
        domain = order_to_domain(row)
        self.session.delete(row)
        self.session.flush()
        return domain

    def next_order_id(self) -> int:
        return next_id(self.session, OrderORM)
