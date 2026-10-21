"""Shopping cart use cases and business rules."""
from __future__ import annotations

from decimal import Decimal

from app.catalog.exceptions import VariantNotFoundError
from app.catalog.models import Product, ProductVariant
from app.catalog.repository import ProductRepository

from .exceptions import CartItemNotFoundError, InsufficientStockError, InvalidCartDataError
from .models import Cart
from .repository import CartRepository


class CartService:
    """Coordinates the cart domain with current catalog data.

    Cart items intentionally store only ``variant_id`` and quantity. Product
    names, prices and stock are read from the current catalog whenever the cart
    is returned. This avoids stale prices and prepares the project for order
    revalidation in v0.5.
    """

    def __init__(self, cart_repository: CartRepository, product_repository: ProductRepository):
        self.cart_repository = cart_repository
        self.product_repository = product_repository

    def get_cart(self, user_id: int) -> dict:
        cart = self._get_or_create_cart(user_id)
        return self._serialize_cart(cart)

    def add_item(self, user_id: int, variant_id: int, quantity: int) -> dict:
        cart = self._get_or_create_cart(user_id)
        _, variant = self._get_variant(variant_id)
        existing = cart.get_item(variant_id)
        requested_quantity = quantity + (existing.quantity if existing else 0)
        self._assert_stock(variant, requested_quantity)

        try:
            cart.add_item(variant_id, quantity)
        except ValueError as exc:
            raise InvalidCartDataError(str(exc)) from exc
        self.cart_repository.save(cart)
        return self._serialize_cart(cart)

    def update_item(self, user_id: int, variant_id: int, quantity: int) -> dict:
        cart = self._get_or_create_cart(user_id)
        if cart.get_item(variant_id) is None:
            raise CartItemNotFoundError('Позиция не найдена в корзине')

        _, variant = self._get_variant(variant_id)
        self._assert_stock(variant, quantity)
        try:
            cart.set_quantity(variant_id, quantity)
        except ValueError as exc:
            raise InvalidCartDataError(str(exc)) from exc
        self.cart_repository.save(cart)
        return self._serialize_cart(cart)

    def remove_item(self, user_id: int, variant_id: int) -> None:
        cart = self._get_or_create_cart(user_id)
        if cart.remove_item(variant_id) is None:
            raise CartItemNotFoundError('Позиция не найдена в корзине')
        self.cart_repository.save(cart)

    def clear_cart(self, user_id: int) -> None:
        cart = self._get_or_create_cart(user_id)
        cart.clear()
        self.cart_repository.save(cart)

    def _get_or_create_cart(self, user_id: int) -> Cart:
        self.cart_repository.lock_user(user_id)
        cart = self.cart_repository.get_by_user_id(user_id)
        if cart is not None:
            return cart
        try:
            cart = Cart(user_id=user_id)
        except ValueError as exc:
            raise InvalidCartDataError(str(exc)) from exc
        return self.cart_repository.save(cart)

    def _get_variant(self, variant_id: int) -> tuple[Product, ProductVariant]:
        found = self.product_repository.find_variant(variant_id)
        if found is None:
            raise VariantNotFoundError('Вариант товара не найден')
        return found

    @staticmethod
    def _assert_stock(variant: ProductVariant, quantity: int) -> None:
        if quantity > variant.stock:
            raise InsufficientStockError(
                f'Недостаточно товара на складе: доступно {variant.stock}, запрошено {quantity}'
            )

    def _serialize_cart(self, cart: Cart) -> dict:
        items: list[dict] = []
        subtotal = Decimal('0.00')
        stale_variant_ids: list[int] = []

        variants = self.product_repository.find_variants([item.variant_id for item in cart.items])
        images = {}
        session = getattr(self.product_repository, 'session', None)
        if session is not None and variants:
            from .images import product_images
            images = product_images(session, {product.id for product, _ in variants.values()})
        for cart_item in cart.items:
            found = variants.get(cart_item.variant_id)
            if found is None:
                # A variant may be deleted by catalog CRUD after it was placed
                # into a cart. Removing that stale reference keeps GET /cart
                # usable instead of making the entire cart impossible to read.
                stale_variant_ids.append(cart_item.variant_id)
                continue

            product, variant = found
            line_total = (variant.price * cart_item.quantity).quantize(Decimal('0.01'))
            subtotal += line_total
            items.append({
                'product_id': product.id,
                'product_name': product.name,
                'image_url': images.get(product.id, getattr(product, 'image_url', None)),
                'variant_id': variant.id,
                'sku': variant.sku,
                'label': variant.label,
                'unit_price': str(variant.price),
                'original_unit_price': str(variant.original_price) if variant.original_price is not None else None,
                'currency': variant.currency,
                'quantity': cart_item.quantity,
                'available_stock': variant.stock,
                'is_available': variant.stock >= cart_item.quantity,
                'line_total': str(line_total),
            })

        if stale_variant_ids:
            for variant_id in stale_variant_ids:
                cart.remove_item(variant_id)
            self.cart_repository.save(cart)

        total_items = sum(item['quantity'] for item in items)
        can_checkout = bool(items) and all(item['is_available'] for item in items)
        return {
            'user_id': cart.user_id,
            'items': items,
            'total_items': total_items,
            'subtotal': str(subtotal.quantize(Decimal('0.01'))),
            'currency': 'KZT',
            'can_checkout': can_checkout,
        }
