"""Catalog use cases and business rules."""
from __future__ import annotations

from decimal import Decimal

from .exceptions import (
    DuplicateSKUError,
    InvalidCatalogDataError,
    ProductNotFoundError,
    VariantNotFoundError,
)
from .models import Accessory, Food, Product, ProductVariant
from .repository import ProductRepository
from .schemas import ProductCreate, ProductUpdate, VariantCreate, VariantUpdate
from .types import PRODUCT_KINDS
from .search import product_matches_search


class CatalogService:
    def __init__(self, repository: ProductRepository):
        self.repository = repository

    def list_products(
        self,
        *,
        q: str | None = None,
        pet_type: str | None = None,
        category: str | None = None,
        product_kind: str | None = None,
        brand: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        in_stock: bool | None = None,
        hits_only: bool = False,
        sort: str = 'id',
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        if min_price is not None and max_price is not None and min_price > max_price:
            raise InvalidCatalogDataError('min_price не может превышать max_price')

        page_result = self.repository.query_page(
            q=q, pet_type=pet_type, category=category, product_kind=product_kind, brand=brand, min_price=min_price,
            max_price=max_price, in_stock=in_stock, sort=sort, page=page, page_size=page_size,
            hits_only=hits_only,
        )
        if page_result is not None:
            return page_result

        result: list[tuple[Product, Decimal]] = []

        for product in self.repository.all():
            if hits_only and not product.is_hit:
                continue
            if pet_type and product.pet_type != pet_type:
                continue
            if category and product.category != category:
                continue
            if product_kind and product.product_kind != product_kind:
                continue
            if brand and product.brand.casefold() != brand.strip().casefold():
                continue
            if not product_matches_search(product, q):
                continue

            variants = [
                variant
                for variant in product.variants
                if (min_price is None or variant.price >= min_price)
                and (max_price is None or variant.price <= max_price)
                and (in_stock is None or (variant.stock > 0) == in_stock)
            ]
            if variants:
                result.append((product, min(variant.price for variant in variants)))

        if sort == 'name':
            result.sort(key=lambda item: (item[0].name.casefold(), item[0].id))
        elif sort in ('price_asc', 'price_desc'):
            result.sort(
                key=lambda item: (
                    item[1] if sort == 'price_asc' else -item[1],
                    item[0].id,
                )
            )
        else:
            result.sort(key=lambda item: item[0].id)

        start = (page - 1) * page_size
        return {
            'items': [product.to_dict() for product, _ in result[start:start + page_size]],
            'total': len(result),
            'page': page,
            'page_size': page_size,
        }

    def get_product(self, product_id: int) -> Product:
        product = self.repository.get(product_id)
        if product is None:
            raise ProductNotFoundError('Товар не найден')
        return product

    def set_discount(self, product_id: int, data) -> Product:
        if data.start_at is not None and data.end_at is not None and data.start_at >= data.end_at:
            raise InvalidCatalogDataError('Конец скидки должен быть позже начала')
        return self.repository.set_discount(product_id, data.percent, data.start_at, data.end_at)

    def clear_discount(self, product_id: int) -> None:
        self.repository.set_discount(product_id, None)

    def create_product(self, data: ProductCreate) -> Product:
        self._assert_unique_request_skus(data.variants)
        for variant in data.variants:
            self._assert_sku_available(variant.sku)

        variants = [self._new_variant(variant) for variant in data.variants]
        product_id = self.repository.next_product_id()

        try:
            if data.category == 'food':
                if not data.composition:
                    raise InvalidCatalogDataError('Для категории food поле composition обязательно')
                if data.material is not None:
                    raise InvalidCatalogDataError('Для категории food поле material не используется')
                product: Product = Food(
                    product_id, data.name, data.pet_type, data.brand, variants, data.composition
                )
            else:
                if not data.material:
                    raise InvalidCatalogDataError('Для категории accessory поле material обязательно')
                if data.composition is not None:
                    raise InvalidCatalogDataError('Для категории accessory поле composition не используется')
                product = Accessory(
                    product_id, data.name, data.pet_type, data.brand, variants, data.material
                )
            if data.product_kind is not None:
                product.change_product_kind(data.product_kind)
        except ValueError as exc:
            raise InvalidCatalogDataError(str(exc)) from exc

        return self.repository.add(product)

    def update_product(self, product_id: int, data: ProductUpdate) -> Product:
        self.repository.lock_product(product_id)
        product = self.get_product(product_id)
        changes = data.model_dump(exclude_unset=True)
        if any(value is None for value in changes.values()):
            raise InvalidCatalogDataError('Поля PATCH не могут иметь значение null')

        if 'composition' in changes and not isinstance(product, Food):
            raise InvalidCatalogDataError('Поле composition доступно только для food')
        if 'material' in changes and not isinstance(product, Accessory):
            raise InvalidCatalogDataError('Поле material доступно только для accessory')

        try:
            if 'name' in changes:
                product.rename(changes['name'])
            if 'pet_type' in changes:
                product.change_pet_type(changes['pet_type'])
            if 'brand' in changes:
                product.change_brand(changes['brand'])
            if 'product_kind' in changes:
                product.change_product_kind(changes['product_kind'])
            if 'composition' in changes:
                product.change_composition(changes['composition'])
            if 'material' in changes:
                product.change_material(changes['material'])
        except ValueError as exc:
            raise InvalidCatalogDataError(str(exc)) from exc

        return self.repository.update_product_fields(product, set(changes))

    def delete_product(self, product_id: int) -> None:
        if self.repository.delete(product_id) is None:
            raise ProductNotFoundError('Товар не найден')

    def add_variant(self, product_id: int, data: VariantCreate) -> ProductVariant:
        self.repository.lock_product(product_id)
        product = self.get_product(product_id)
        self._assert_sku_available(data.sku)
        variant = self._new_variant(data)
        try:
            product.add_variant(variant)
        except ValueError as exc:
            raise InvalidCatalogDataError(str(exc)) from exc
        self.repository.add_variant(product, variant)
        return variant

    def update_variant(self, product_id: int, variant_id: int, data: VariantUpdate) -> ProductVariant:
        product = self.get_product(product_id)
        variant = product.get_variant(variant_id)
        if variant is None:
            raise VariantNotFoundError('Вариант товара не найден')

        changes = data.model_dump(exclude_unset=True)
        if any(value is None for value in changes.values()):
            raise InvalidCatalogDataError('Поля PATCH не могут иметь значение null')
        if 'sku' in changes:
            self._assert_sku_available(changes['sku'], exclude_variant_id=variant_id)

        try:
            if 'sku' in changes:
                variant.change_sku(changes['sku'])
            if 'label' in changes:
                variant.change_label(changes['label'])
            if 'price' in changes:
                variant.change_price(changes['price'])
            if 'stock' in changes:
                variant.set_stock(changes['stock'])
        except ValueError as exc:
            raise InvalidCatalogDataError(str(exc)) from exc
        self.repository.update_variant_fields(product, variant, set(changes))
        return variant

    def delete_variant(self, product_id: int, variant_id: int) -> None:
        self.repository.lock_product(product_id)
        product = self.get_product(product_id)
        if product.get_variant(variant_id) is None:
            raise VariantNotFoundError('Вариант товара не найден')
        try:
            product.remove_variant(variant_id)
        except ValueError as exc:
            raise InvalidCatalogDataError(str(exc)) from exc
        self.repository.remove_variant(product, variant_id)

    def categories(self) -> list[dict[str, str]]:
        return [
            {'id': 'food', 'name': 'Корма'},
            {'id': 'accessory', 'name': 'Аксессуары'},
        ]

    def brands(self) -> list[str]:
        return self.repository.brands()

    def product_kinds(self, *, pet_type: str | None = None) -> list[dict]:
        counts = self.repository.product_kind_counts(pet_type=pet_type)
        return [{'id': kind, 'name': name, 'count': counts.get(kind, 0)} for kind, name in PRODUCT_KINDS]

    def _new_variant(self, data: VariantCreate) -> ProductVariant:
        try:
            return ProductVariant(
                self.repository.next_variant_id(),
                data.sku,
                data.label,
                data.price,
                data.stock,
            )
        except ValueError as exc:
            raise InvalidCatalogDataError(str(exc)) from exc

    def _assert_sku_available(self, sku: str, exclude_variant_id: int | None = None) -> None:
        if self.repository.sku_exists(sku, exclude_variant_id=exclude_variant_id):
            raise DuplicateSKUError(f'SKU "{sku}" уже существует')

    @staticmethod
    def _assert_unique_request_skus(variants: list[VariantCreate]) -> None:
        normalized = [variant.sku.casefold() for variant in variants]
        if len(normalized) != len(set(normalized)):
            raise DuplicateSKUError('SKU внутри создаваемого товара должны быть уникальными')
