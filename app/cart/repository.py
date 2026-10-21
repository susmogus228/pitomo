"""Repository abstraction for shopping carts."""
from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.db.mappers import cart_to_domain
from app.db.models import CartItemORM, CartORM, UserORM
from app.users.exceptions import UserNotFoundError

from .models import Cart


class CartRepository(ABC):
    def lock_user(self, user_id: int) -> None:
        """Lock stable owner row before accessing mutable cart state."""

    @abstractmethod
    def get_by_user_id(self, user_id: int) -> Cart | None:
        raise NotImplementedError

    @abstractmethod
    def save(self, cart: Cart) -> Cart:
        raise NotImplementedError


class InMemoryCartRepository(CartRepository):
    def __init__(self, carts: list[Cart] | tuple[Cart, ...] = ()):
        self.__carts = {cart.user_id: cart for cart in carts}

    def get_by_user_id(self, user_id: int) -> Cart | None:
        return self.__carts.get(user_id)

    def save(self, cart: Cart) -> Cart:
        self.__carts[cart.user_id] = cart
        return cart


class SQLAlchemyCartRepository(CartRepository):
    def __init__(self, session: Session):
        self.session = session

    def lock_user(self, user_id: int) -> None:
        if self.session.get_bind().dialect.name == 'sqlite':
            # SQLite has one writer. Acquire its write lock before the cart read.
            self.session.execute(update(UserORM).where(UserORM.id == user_id).values(id=UserORM.id))
        row = self.session.scalar(select(UserORM.id).where(UserORM.id == user_id).with_for_update())
        if row is None:
            raise UserNotFoundError('Пользователь не найден')

    def get_by_user_id(self, user_id: int) -> Cart | None:
        row = self.session.scalar(
            select(CartORM)
            .where(CartORM.user_id == user_id)
            .options(selectinload(CartORM.items)).execution_options(populate_existing=True)
        )
        return cart_to_domain(row) if row is not None else None

    def save(self, cart: Cart) -> Cart:
        row = self.session.scalar(
            select(CartORM)
            .where(CartORM.user_id == cart.user_id)
            .options(selectinload(CartORM.items)).execution_options(populate_existing=True)
        )
        if row is None:
            row = CartORM(user_id=cart.user_id)
            self.session.add(row)
            self.session.flush()

        existing = {item.variant_id: item for item in row.items}
        wanted = {item.variant_id: item for item in cart.items}
        for variant_id, item in existing.items():
            if variant_id not in wanted:
                row.items.remove(item)
        for variant_id, item in wanted.items():
            if variant_id in existing:
                existing[variant_id].quantity = item.quantity
            else:
                row.items.append(CartItemORM(variant_id=variant_id, quantity=item.quantity))
        self.session.flush()
        return cart
