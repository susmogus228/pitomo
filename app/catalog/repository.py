"""Repository abstraction plus in-memory and SQLAlchemy implementations."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update, delete, or_, and_, case, cast, Numeric
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.mappers import product_to_domain
from app.db.models import ProductORM, ProductVariantORM, OrderORM, OrderItemORM
from .pricing import active_discount_percent
from .search import product_search_criteria
from app.db.identifiers import next_id
from app.db.errors import unique_violation
from .exceptions import DuplicateSKUError, ProductNotFoundError, VariantNotFoundError
from .models import ProductVariant

from .models import Accessory, Food, Product


class ProductRepository(ABC):
    """Storage contract used by CatalogService."""

    @abstractmethod
    def all(self) -> tuple[Product, ...]:
        raise NotImplementedError

    @abstractmethod
    def get(self, product_id: int) -> Product | None:
        raise NotImplementedError

    @abstractmethod
    def add(self, product: Product) -> Product:
        raise NotImplementedError

    @abstractmethod
    def save(self, product: Product) -> Product:
        raise NotImplementedError

    @abstractmethod
    def delete(self, product_id: int) -> Product | None:
        raise NotImplementedError

    @abstractmethod
    def next_product_id(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def next_variant_id(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def sku_exists(self, sku: str, exclude_variant_id: int | None = None) -> bool:
        raise NotImplementedError

    @abstractmethod
    def find_variant(self, variant_id: int, *, for_update: bool = False):
        """Return ``(product, variant)`` for a global variant id, if it exists."""
        raise NotImplementedError

    @abstractmethod
    def set_variant_stock(self, variant_id: int, stock: int) -> None:
        """Persist only one SKU stock value without rewriting sibling variants."""
        raise NotImplementedError

    def lock_product(self, product_id: int) -> None:
        """Serialize structural variant changes; in-memory usage is sequential."""

    def update_product_fields(self, product: Product, fields: set[str]) -> Product:
        return self.save(product)

    def add_variant(self, product: Product, variant: ProductVariant) -> None:
        self.save(product)

    def update_variant_fields(self, product: Product, variant: ProductVariant, fields: set[str]) -> None:
        self.save(product)

    def remove_variant(self, product: Product, variant_id: int) -> None:
        self.save(product)

    def find_variants(self, variant_ids: list[int]) -> dict:
        return {variant_id: found for variant_id in variant_ids if (found := self.find_variant(variant_id)) is not None}

    def query_page(self, **filters):
        return None

    def brands(self) -> list[str]:
        return sorted({product.brand for product in self.all()})

    def product_kind_counts(self, *, pet_type: str | None = None) -> dict[str, int]:
        counts: dict[str, int] = {}
        for product in self.all():
            if product.product_kind is not None and (pet_type is None or product.pet_type == pet_type):
                counts[product.product_kind] = counts.get(product.product_kind, 0) + 1
        return counts

    def hit_ids(self) -> set[int]:
        return set()

    def set_discount(self, product_id: int, percent: int | None,
                     start_at: datetime | None = None, end_at: datetime | None = None) -> Product:
        product = self.get(product_id)
        if product is None:
            raise ProductNotFoundError('Товар не найден')
        product.discount_percent = percent
        product.discount_start_at = start_at
        product.discount_end_at = end_at
        for variant in product.variants:
            variant.discount_percent = active_discount_percent(percent, start_at, end_at)
            variant.original_price = variant.base_price if variant.discount_percent else None
        return self.save(product)


class InMemoryProductRepository(ProductRepository):
    """Legacy repository retained for isolated domain tests and examples."""

    def __init__(self, products: list[Product] | tuple[Product, ...] = ()):
        self.__products = {product.id: product for product in products}
        self.__next_product_id = max(self.__products, default=0) + 1
        variant_ids = [variant.id for product in self.__products.values() for variant in product.variants]
        self.__next_variant_id = max(variant_ids, default=0) + 1

    def all(self) -> tuple[Product, ...]:
        return tuple(self.__products.values())

    def get(self, product_id: int) -> Product | None:
        return self.__products.get(product_id)

    def add(self, product: Product) -> Product:
        self.__products[product.id] = product
        return product

    def save(self, product: Product) -> Product:
        self.__products[product.id] = product
        return product

    def delete(self, product_id: int) -> Product | None:
        return self.__products.pop(product_id, None)

    def next_product_id(self) -> int:
        value = self.__next_product_id
        self.__next_product_id += 1
        return value

    def next_variant_id(self) -> int:
        value = self.__next_variant_id
        self.__next_variant_id += 1
        return value

    def sku_exists(self, sku: str, exclude_variant_id: int | None = None) -> bool:
        normalized = sku.strip().casefold()
        return any(
            variant.id != exclude_variant_id and variant.sku.casefold() == normalized
            for product in self.__products.values()
            for variant in product.variants
        )

    def find_variant(self, variant_id: int, *, for_update: bool = False):
        for product in self.__products.values():
            variant = product.get_variant(variant_id)
            if variant is not None:
                return product, variant
        return None

    def set_variant_stock(self, variant_id: int, stock: int) -> None:
        found = self.find_variant(variant_id)
        if found is None:
            raise KeyError(variant_id)
        _, variant = found
        variant.set_stock(stock)


class SQLAlchemyProductRepository(ProductRepository):
    """SQLAlchemy persistence adapter for catalog domain objects."""

    def __init__(self, session: Session):
        self.session = session
        self._next_product_id_cache: int | None = None
        self._next_variant_id_cache: int | None = None

    def all(self) -> tuple[Product, ...]:
        rows = self.session.scalars(
            select(ProductORM)
            .options(selectinload(ProductORM.variants))
            .order_by(ProductORM.id)
        ).all()
        hits = self.hit_ids()
        products = tuple(product_to_domain(row) for row in rows)
        for product in products:
            product.is_hit = product.id in hits
        return products

    def get(self, product_id: int) -> Product | None:
        row = self.session.scalar(
            select(ProductORM)
            .where(ProductORM.id == product_id)
            .options(selectinload(ProductORM.variants))
        )
        if row is None:
            return None
        product = product_to_domain(row)
        product.is_hit = product.id in self.hit_ids()
        return product

    def add(self, product: Product) -> Product:
        return self.save(product)

    def save(self, product: Product) -> Product:
        row = self.session.scalar(
            select(ProductORM)
            .where(ProductORM.id == product.id)
            .options(selectinload(ProductORM.variants))
        )
        if row is None:
            row = ProductORM(id=product.id)
            self.session.add(row)

        row.image_url = product.image_url
        row.name = product.name
        row.pet_type = product.pet_type
        row.brand = product.brand
        row.category = product.category
        row.product_kind = product.product_kind
        row.composition = product.composition if isinstance(product, Food) else None
        row.material = product.material if isinstance(product, Accessory) else None

        existing = {variant.id: variant for variant in row.variants}
        wanted_ids = {variant.id for variant in product.variants}
        for variant_row in list(row.variants):
            if variant_row.id not in wanted_ids:
                row.variants.remove(variant_row)

        for variant in product.variants:
            variant_row = existing.get(variant.id)
            if variant_row is None:
                variant_row = ProductVariantORM(id=variant.id)
                row.variants.append(variant_row)
            variant_row.sku = variant.sku
            variant_row.label = variant.label
            variant_row.price = variant.base_price
            variant_row.currency = variant.currency
            variant_row.stock = variant.stock

        self._flush()
        return product

    def delete(self, product_id: int) -> Product | None:
        row = self.session.scalar(
            select(ProductORM)
            .where(ProductORM.id == product_id)
            .options(selectinload(ProductORM.variants))
        )
        if row is None:
            return None
        domain = product_to_domain(row)
        self.session.delete(row)
        self.session.flush()
        return domain

    def next_product_id(self) -> int:
        return next_id(self.session, ProductORM)

    def next_variant_id(self) -> int:
        return next_id(self.session, ProductVariantORM)

    def sku_exists(self, sku: str, exclude_variant_id: int | None = None) -> bool:
        statement = select(ProductVariantORM.id).where(ProductVariantORM.sku_normalized == sku.strip().casefold())
        if exclude_variant_id is not None:
            statement = statement.where(ProductVariantORM.id != exclude_variant_id)
        return self.session.scalar(statement.limit(1)) is not None

    def _flush(self):
        try:
            self.session.flush()
        except IntegrityError as exc:
            self._translate_duplicate(exc)

    @staticmethod
    def _translate_duplicate(exc):
        if unique_violation(exc, names={'uq_product_variants_sku_normalized', 'ix_product_variants_sku', 'product_variants_sku_key'},
                            sqlite_columns={'product_variants.sku', 'product_variants.sku_normalized'}):
            raise DuplicateSKUError('SKU уже существует') from exc
        raise exc

    def lock_product(self, product_id: int) -> None:
        if self.session.get_bind().dialect.name == 'sqlite':
            self.session.execute(update(ProductORM).where(ProductORM.id == product_id).values(id=ProductORM.id))
        self.session.execute(select(ProductORM.id).where(ProductORM.id == product_id).with_for_update())

    def update_product_fields(self, product: Product, fields: set[str]) -> Product:
        allowed = {'name', 'pet_type', 'brand', 'composition', 'material', 'product_kind'}
        if not fields <= allowed:
            raise ValueError('Unsupported product fields')
        values = {field: getattr(product, field) for field in fields}
        if 'name' in values:
            values['name_normalized'] = product.name.casefold()
        if 'brand' in values:
            values['brand_normalized'] = product.brand.casefold()
        if values:
            result = self.session.execute(update(ProductORM).where(ProductORM.id == product.id).values(**values))
            if result.rowcount != 1:
                raise ProductNotFoundError('Товар не найден')
        self.session.flush()
        self.session.expire_all()
        return self.get(product.id)

    def add_variant(self, product: Product, variant: ProductVariant) -> None:
        self.session.add(ProductVariantORM(
            id=variant.id, product_id=product.id, sku=variant.sku, label=variant.label,
            price=variant.price, currency=variant.currency, stock=variant.stock,
        ))
        self._flush()

    def update_variant_fields(self, product: Product, variant: ProductVariant, fields: set[str]) -> None:
        allowed = {'sku', 'label', 'price', 'stock'}
        if not fields <= allowed:
            raise ValueError('Unsupported variant fields')
        values = {field: (variant.base_price if field == 'price' else getattr(variant, field))
                  for field in fields}
        if 'sku' in values:
            values['sku_normalized'] = variant.sku.casefold()
        if values:
            try:
                result = self.session.execute(update(ProductVariantORM).where(
                    ProductVariantORM.id == variant.id, ProductVariantORM.product_id == product.id,
                ).values(**values))
                if result.rowcount != 1:
                    raise VariantNotFoundError('Вариант товара не найден')
                self._flush()
            except IntegrityError as exc:
                self._translate_duplicate(exc)

    def remove_variant(self, product: Product, variant_id: int) -> None:
        self.session.execute(delete(ProductVariantORM).where(
            ProductVariantORM.id == variant_id, ProductVariantORM.product_id == product.id,
        ))
        self.session.flush()

    @staticmethod
    def _project_variant(row):
        variant = ProductVariant(row.id, row.sku, row.label, row.price, row.stock)
        active = active_discount_percent(row.discount_percent, row.discount_start_at, row.discount_end_at)
        if active is not None:
            variant.discount_percent = active
            variant.original_price = variant.base_price
        # A lightweight projection avoids loading or caching sibling SKU stock.
        from types import SimpleNamespace
        return SimpleNamespace(id=row.product_id, name=row.product_name), variant

    def _variant_select(self):
        return select(
            ProductVariantORM.id, ProductVariantORM.product_id, ProductVariantORM.sku,
            ProductVariantORM.label, ProductVariantORM.price, ProductVariantORM.stock,
            ProductORM.name.label('product_name'),
            ProductORM.discount_percent, ProductORM.discount_start_at, ProductORM.discount_end_at,
        ).join(ProductORM, ProductORM.id == ProductVariantORM.product_id)

    def find_variant(self, variant_id: int, *, for_update: bool = False):
        statement = self._variant_select().where(ProductVariantORM.id == variant_id)
        if for_update:
            statement = statement.with_for_update(of=ProductVariantORM)
        row = self.session.execute(statement).first()
        return self._project_variant(row) if row is not None else None

    def find_variants(self, variant_ids: list[int]) -> dict:
        if not variant_ids:
            return {}
        rows = self.session.execute(self._variant_select().where(ProductVariantORM.id.in_(variant_ids))).all()
        return {row.id: self._project_variant(row) for row in rows}

    def set_variant_stock(self, variant_id: int, stock: int) -> None:
        result = self.session.execute(update(ProductVariantORM).where(ProductVariantORM.id == variant_id).values(stock=stock))
        if result.rowcount != 1:
            raise KeyError(variant_id)
        self.session.flush()

    def brands(self) -> list[str]:
        return list(self.session.scalars(select(ProductORM.brand).distinct().order_by(ProductORM.brand)))

    def product_kind_counts(self, *, pet_type=None):
        statement = select(ProductORM.product_kind, func.count(ProductORM.id)).where(
            ProductORM.product_kind.is_not(None))
        if pet_type is not None:
            statement = statement.where(ProductORM.pet_type == pet_type)
        return dict(self.session.execute(statement.group_by(ProductORM.product_kind)).all())

    def hit_ids(self) -> set[int]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        sold = func.sum(OrderItemORM.quantity)
        statement = (select(OrderItemORM.product_id)
                     .join(OrderORM, OrderORM.id == OrderItemORM.order_id)
                     .where(OrderORM.status == 'created',
                            or_(and_(OrderORM.payment_method == 'demo',
                                     OrderORM.payment_status == 'demo_paid', OrderORM.paid_at >= cutoff),
                                and_(OrderORM.payment_method == 'cod', OrderORM.received_at >= cutoff)))
                     .group_by(OrderItemORM.product_id).having(sold >= 2)
                     .order_by(sold.desc(), OrderItemORM.product_id).limit(8))
        return set(self.session.scalars(statement))

    def set_discount(self, product_id: int, percent: int | None,
                     start_at: datetime | None = None, end_at: datetime | None = None) -> Product:
        self.lock_product(product_id)
        row = self.session.get(ProductORM, product_id)
        if row is None:
            raise ProductNotFoundError('Товар не найден')
        row.discount_percent = percent
        row.discount_start_at = start_at if percent is not None else None
        row.discount_end_at = end_at if percent is not None else None
        self.session.flush()
        self.session.expire_all()
        return self.get(product_id)

    def query_page(self, *, q=None, pet_type=None, category=None, product_kind=None, brand=None,
                   min_price=None, max_price=None, in_stock=None, hits_only=False,
                   sort='id', page=1, page_size=20, stock_max=None):
        now = datetime.now(timezone.utc)
        active = and_(ProductORM.discount_percent.is_not(None),
                      or_(ProductORM.discount_start_at.is_(None), ProductORM.discount_start_at <= now),
                      or_(ProductORM.discount_end_at.is_(None), ProductORM.discount_end_at > now))
        effective_price = case((active, cast(func.round(
            ProductVariantORM.price * (100 - ProductORM.discount_percent) / 100, 2), Numeric(12, 2))),
            else_=ProductVariantORM.price)
        variants = (select(ProductVariantORM.product_id, func.min(effective_price).label('sort_price'))
                    .join(ProductORM, ProductORM.id == ProductVariantORM.product_id))
        if min_price is not None:
            variants = variants.where(effective_price >= min_price)
        if max_price is not None:
            variants = variants.where(effective_price <= max_price)
        if in_stock is not None:
            variants = variants.where((ProductVariantORM.stock > 0) if in_stock else (ProductVariantORM.stock == 0))
        if stock_max is not None:
            variants = variants.where(ProductVariantORM.stock <= stock_max)
        matched = variants.group_by(ProductVariantORM.product_id).subquery()
        statement = select(ProductORM).join(matched, matched.c.product_id == ProductORM.id)
        hits = self.hit_ids()
        if hits_only:
            statement = statement.where(ProductORM.id.in_(hits))
        if pet_type:
            statement = statement.where(ProductORM.pet_type == pet_type)
        if category:
            statement = statement.where(ProductORM.category == category)
        if product_kind:
            statement = statement.where(ProductORM.product_kind == product_kind)
        if brand:
            statement = statement.where(ProductORM.brand_normalized == brand.strip().casefold())
        statement = statement.where(*product_search_criteria(q))
        total = self.session.scalar(select(func.count()).select_from(statement.subquery()))
        if sort == 'name':
            statement = statement.order_by(ProductORM.name_normalized, ProductORM.id)
        elif sort in {'price_asc', 'price_desc'}:
            price = matched.c.sort_price
            statement = statement.order_by(price if sort == 'price_asc' else price.desc(), ProductORM.id)
        else:
            statement = statement.order_by(ProductORM.id)
        rows = self.session.scalars(statement.options(selectinload(ProductORM.variants))
                                    .limit(page_size).offset((page - 1) * page_size)).all()
        items = []
        for row in rows:
            product = product_to_domain(row)
            product.is_hit = product.id in hits
            items.append(product.to_dict())
        return {'items': items,
                'total': total, 'page': page, 'page_size': page_size}
