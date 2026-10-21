"""Mapping helpers between SQLAlchemy rows and pure domain objects."""
from __future__ import annotations

from app.cart.models import Cart
from app.catalog.models import Accessory, Food, Product, ProductVariant
from app.orders.models import DeliveryTracking, Order, OrderItem
from app.users.models import User

from .models import CartORM, OrderORM, ProductORM, UserORM


def product_to_domain(row: ProductORM) -> Product:
    from app.catalog.pricing import active_discount_percent
    active_discount = active_discount_percent(row.discount_percent, row.discount_start_at,
                                              row.discount_end_at)
    variants = [
        ProductVariant(
            id=item.id,
            sku=item.sku,
            label=item.label,
            price=item.price,
            stock=item.stock,
        )
        for item in row.variants
    ]
    for variant in variants:
        if active_discount is not None:
            variant.discount_percent = active_discount
            variant.original_price = variant.base_price
    if row.category == 'food':
        product = Food(
            row.id, row.name, row.pet_type, row.brand, variants,
            composition=row.composition or '',
        )
    else:
        product = Accessory(
            row.id, row.name, row.pet_type, row.brand, variants,
            material=row.material or '',
        )
    product.image_url = row.image_url
    product.discount_percent = row.discount_percent
    product.discount_start_at = row.discount_start_at
    product.discount_end_at = row.discount_end_at
    product.change_product_kind(row.product_kind)
    return product


def user_to_domain(row: UserORM) -> User:
    return User(
        id=row.id,
        email=row.email,
        password_hash=row.password_hash,
        first_name=row.first_name,
        last_name=row.last_name,
        is_active=row.is_active,
        role=row.role,
    )


def cart_to_domain(row: CartORM) -> Cart:
    cart = Cart(user_id=row.user_id)
    for item in row.items:
        cart.add_item(item.variant_id, item.quantity)
    return cart


def order_to_domain(row: OrderORM) -> Order:
    items = [
        OrderItem(
            product_id=item.product_id,
            product_name=item.product_name,
            variant_id=item.variant_id,
            sku=item.sku,
            variant_label=item.variant_label,
            unit_price=item.unit_price,
            original_unit_price=item.original_unit_price,
            quantity=item.quantity,
            currency=item.currency,
        )
        for item in row.items
    ]
    return Order(
        id=row.id,
        user_id=row.user_id,
        items=items,
        created_at=row.created_at,
        status=row.status,
        contact_name=row.contact_name,
        phone=row.phone,
        delivery_method=row.delivery_method,
        address=row.address,
        comment=row.comment,
        payment_method=row.payment_method,
        payment_status=row.payment_status,
        checkout_fingerprint=row.checkout_fingerprint,
        paid_at=row.paid_at,
        received_at=row.received_at,
        delivery_lat=row.delivery_lat,
        delivery_lon=row.delivery_lon,
        delivery_tracking=DeliveryTracking(
            stage=row.delivery_stage or ('nearby' if row.received_at else 'warehouse'),
            incident=row.delivery_incident, incident_note=row.delivery_incident_note,
            updated_at=row.delivery_updated_at, version=row.delivery_version,
            history=row.delivery_history,
        ) if row.delivery_method == 'delivery' else None,

    )
