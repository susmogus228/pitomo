"""Domain entities for the shopping cart.

The cart model contains no FastAPI, Pydantic, SQL or storage imports. It keeps
cart state and quantity invariants inside the domain layer.
"""
from __future__ import annotations


class CartItem:
    """A reference to one purchasable catalog variant and its quantity."""

    def __init__(self, variant_id: int, quantity: int):
        if type(variant_id) is not int or not 1 <= variant_id <= 2147483647:
            raise ValueError('variant_id должен быть положительным целым числом')
        self.variant_id = variant_id
        self.set_quantity(quantity)

    def set_quantity(self, quantity: int) -> None:
        if type(quantity) is not int or not 1 <= quantity <= 10000:
            raise ValueError('Количество должно быть положительным целым числом')
        self.quantity = quantity

    def increase(self, quantity: int) -> None:
        if type(quantity) is not int or not 1 <= quantity <= 10000:
            raise ValueError('Добавляемое количество должно быть положительным целым числом')
        self.set_quantity(self.quantity + quantity)


class Cart:
    """One shopping cart owned by one application user."""

    def __init__(self, user_id: int, items: list[CartItem] | tuple[CartItem, ...] = ()):
        if type(user_id) is not int or not 1 <= user_id <= 2147483647:
            raise ValueError('user_id должен быть положительным целым числом')
        self.user_id = user_id
        self.__items: dict[int, CartItem] = {}
        for item in items:
            if item.variant_id in self.__items:
                raise ValueError('В корзине не может быть двух строк одного variant_id')
            self.__items[item.variant_id] = item

    @property
    def items(self) -> tuple[CartItem, ...]:
        return tuple(self.__items.values())

    @property
    def total_items(self) -> int:
        return sum(item.quantity for item in self.__items.values())

    def get_item(self, variant_id: int) -> CartItem | None:
        return self.__items.get(variant_id)

    def add_item(self, variant_id: int, quantity: int) -> CartItem:
        existing = self.get_item(variant_id)
        if existing is not None:
            existing.increase(quantity)
            return existing
        item = CartItem(variant_id, quantity)
        self.__items[variant_id] = item
        return item

    def set_quantity(self, variant_id: int, quantity: int) -> CartItem | None:
        item = self.get_item(variant_id)
        if item is None:
            return None
        item.set_quantity(quantity)
        return item

    def remove_item(self, variant_id: int) -> CartItem | None:
        return self.__items.pop(variant_id, None)

    def clear(self) -> None:
        self.__items.clear()
