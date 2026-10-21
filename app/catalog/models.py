"""Domain entities for the catalog.

This module deliberately has no FastAPI, Pydantic, SQL or storage imports.
It contains the OOP model and its invariants only.
"""
from __future__ import annotations

from decimal import Decimal
from .types import PET_TYPES, PRODUCT_KIND_IDS


class ProductVariant:
    """A purchasable SKU of a product."""

    def __init__(self, id: int, sku: str, label: str, price: str | Decimal, stock: int):
        if type(id) is not int or not 1 <= id <= 2147483647:
            raise ValueError("ID должен быть целым числом от 1 до 2147483647")
        self.id = id
        self.sku = self._required_text(sku, 'SKU')
        self.label = self._required_text(label, 'Название варианта')
        self.currency = 'KZT'
        self.change_price(price)
        self.discount_percent: int | None = None
        self.original_price: Decimal | None = None
        self.set_stock(stock)

    @staticmethod
    def _required_text(value: str, field_name: str) -> str:
        if value is None:
            raise ValueError(f'{field_name} не может быть пустым')
        value = str(value).strip()
        if not value:
            raise ValueError(f'{field_name} не может быть пустым')
        return value

    @property
    def price(self) -> Decimal:
        if self.discount_percent is not None:
            from .pricing import discounted_price
            return discounted_price(self.__price, self.discount_percent)
        return self.__price

    @property
    def base_price(self) -> Decimal:
        return self.__price

    @property
    def stock(self) -> int:
        return self.__stock

    def change_sku(self, value: str) -> None:
        self.sku = self._required_text(value, 'SKU')

    def change_label(self, value: str) -> None:
        self.label = self._required_text(value, 'Название варианта')

    def change_price(self, value: str | Decimal) -> None:
        price = Decimal(str(value))
        if not price.is_finite() or not 0 <= price <= Decimal("9999999999.99") or price != price.quantize(Decimal('0.01')):
            raise ValueError('Цена должна быть неотрицательной с максимум 2 знаками после запятой')
        self.__price = price.quantize(Decimal('0.01'))
        if getattr(self, 'discount_percent', None) is not None:
            self.original_price = self.__price

    def set_stock(self, value: int) -> None:
        if type(value) is not int or not 0 <= value <= 2147483647:
            raise ValueError('Остаток должен быть целым неотрицательным числом')
        self.__stock = value

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'sku': self.sku,
            'label': self.label,
            'price': str(self.price),
            'original_price': str(self.original_price) if self.original_price is not None else None,
            'discount_percent': self.discount_percent,
            'currency': self.currency,
            'stock': self.stock,
        }


class Product:
    """Base class for catalog products.

    The concrete category is represented by subclasses rather than by a mutable
    string. This keeps category-specific behavior explicit for the OOP project.
    """

    category = 'product'

    def __init__(self, id: int, name: str, pet_type: str, brand: str, variants: list[ProductVariant]):
        if type(id) is not int or not 1 <= id <= 2147483647:
            raise ValueError("ID должен быть целым числом от 1 до 2147483647")
        self.id = id
        self.image_url: str | None = None
        self.product_kind: str | None = 'food' if self.category == 'food' else None
        self.is_hit = False
        self.discount_percent: int | None = None
        self.discount_start_at = None
        self.discount_end_at = None
        self.rename(name)
        self.change_pet_type(pet_type)
        self.change_brand(brand)
        self.__variants: list[ProductVariant] = list(variants)
        if not self.__variants:
            raise ValueError('У товара должен быть хотя бы один вариант')

    @staticmethod
    def _required_text(value: str, field_name: str) -> str:
        if value is None:
            raise ValueError(f'{field_name} не может быть пустым')
        value = str(value).strip()
        if not value:
            raise ValueError(f'{field_name} не может быть пустым')
        return value

    @property
    def variants(self) -> tuple[ProductVariant, ...]:
        return tuple(self.__variants)

    def rename(self, value: str) -> None:
        self.name = self._required_text(value, 'Название товара')

    def change_brand(self, value: str) -> None:
        self.brand = self._required_text(value, 'Бренд')

    def change_product_kind(self, value: str | None) -> None:
        if value is not None:
            if value not in PRODUCT_KIND_IDS:
                raise ValueError('Неподдерживаемый product_kind')
            if (value in {'food', 'treats'}) != (self.category == 'food'):
                raise ValueError('Раздел товара несовместим с category')
        self.product_kind = value

    def change_pet_type(self, value: str) -> None:
        if value not in PET_TYPES:
            raise ValueError('Неподдерживаемый pet_type')
        self.pet_type = value

    def get_variant(self, variant_id: int) -> ProductVariant | None:
        return next((variant for variant in self.__variants if variant.id == variant_id), None)

    def add_variant(self, variant: ProductVariant) -> None:
        if self.get_variant(variant.id) is not None:
            raise ValueError('Вариант с таким ID уже существует у товара')
        self.__variants.append(variant)

    def remove_variant(self, variant_id: int) -> ProductVariant | None:
        if len(self.__variants) == 1:
            raise ValueError('Нельзя удалить единственный вариант товара')
        for index, variant in enumerate(self.__variants):
            if variant.id == variant_id:
                return self.__variants.pop(index)
        return None

    def get_description(self) -> str:
        return self.name

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'pet_type': self.pet_type,
            'brand': self.brand,
            'category': self.category,
            'product_kind': self.product_kind,
            'description': self.get_description(),
            'composition': getattr(self, 'composition', None),
            'material': getattr(self, 'material', None),
            'image_url': self.image_url,
            'is_hit': self.is_hit,
            'discount_percent': self.discount_percent,
            'discount_start_at': self.discount_start_at,
            'discount_end_at': self.discount_end_at,
            'variants': [variant.to_dict() for variant in self.variants],
        }


class Food(Product):
    category = 'food'

    def __init__(self, id: int, name: str, pet_type: str, brand: str,
                 variants: list[ProductVariant], composition: str):
        super().__init__(id, name, pet_type, brand, variants)
        self.change_composition(composition)

    def change_composition(self, value: str) -> None:
        self.composition = self._required_text(value, 'Состав')

    def get_description(self) -> str:
        return f'{self.name}. Состав: {self.composition}.'


class Accessory(Product):
    category = 'accessory'

    def __init__(self, id: int, name: str, pet_type: str, brand: str,
                 variants: list[ProductVariant], material: str):
        super().__init__(id, name, pet_type, brand, variants)
        self.change_material(material)

    def change_material(self, value: str) -> None:
        self.material = self._required_text(value, 'Материал')

    def get_description(self) -> str:
        return f'{self.name}. Материал: {self.material}.'
