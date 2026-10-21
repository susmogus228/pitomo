"""Repeat a historical order only after confirming current catalog and cart state."""
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth.dependencies import CurrentUser
from app.cart.operations import CartOperations, digest
from app.cart.schemas import CartOperationRequest, CartResponse
from app.db.dependencies import SessionDependency
from app.db.models import OrderORM

router = APIRouter(prefix='/api/v1/orders', tags=['Повтор заказа'])
OrderId = Annotated[int, Path(gt=0, le=2147483647)]


class RepeatItem(BaseModel):
    variant_id: int
    product_id: int
    product_name: str
    label: str
    sku: str
    image_url: str | None
    ordered_quantity: int
    existing_quantity: int
    add_quantity: int
    available_stock: int
    previous_unit_price: str
    unit_price: str | None
    original_unit_price: str | None
    status: Literal['available', 'reduced', 'out_of_stock', 'missing']
    changes: list[str]
    line_total: str


class RepeatPreview(BaseModel):
    order_id: int
    fingerprint: str
    items: list[RepeatItem]
    subtotal: str
    currency: Literal['KZT'] = 'KZT'
    can_repeat: bool


class RepeatRequest(CartOperationRequest):
    fingerprint: str = Field(pattern=r'^[a-f0-9]{64}$')


class RepeatResponse(BaseModel):
    cart: CartResponse
    items: list[RepeatItem]
    replayed: bool = False


def _owned_order(session, user_id, order_id):
    order = session.scalar(select(OrderORM).where(OrderORM.id == order_id, OrderORM.user_id == user_id))
    if order is None:
        raise HTTPException(404, 'Заказ не найден')
    return order


def _preview(operations, order):
    cart = operations.cart()
    catalog = operations.catalog(sorted({item.variant_id for item in order.items}
        | {item.variant_id for item in cart.items}))
    items = []
    subtotal = Decimal('0.00')
    grouped = {}
    for old in order.items:
        if old.variant_id not in grouped:
            grouped[old.variant_id] = [old, 0]
        grouped[old.variant_id][1] += old.quantity
    for old, requested in grouped.values():
        found = catalog.get(old.variant_id)
        existing = cart.get_item(old.variant_id)
        existing_qty = existing.quantity if existing else 0
        row = {'variant_id': old.variant_id, 'product_id': old.product_id,
            'product_name': old.product_name, 'label': old.variant_label, 'sku': old.sku,
            'image_url': None, 'ordered_quantity': requested, 'existing_quantity': existing_qty,
            'add_quantity': 0, 'available_stock': 0, 'previous_unit_price': str(old.unit_price),
            'unit_price': None, 'original_unit_price': None, 'status': 'missing',
            'changes': ['Вариант удалён из каталога'], 'line_total': '0.00'}
        if found is not None:
            variant, product, price = found['variant'], found['product'], found['price']
            added = operations.allowed(cart, variant.id, requested, variant.stock)
            changes = []
            if product.name != old.product_name or variant.sku != old.sku or variant.label != old.variant_label:
                changes.append('Название или упаковка товара изменились')
            if price != old.unit_price:
                changes.append(f'Цена изменилась: {old.unit_price} → {price} ₸')
            if added < requested:
                changes.append(f'Можно добавить {added} из {requested}: учтены остаток и текущая корзина')
            total = (price * added).quantize(Decimal('0.01'))
            subtotal += total
            row.update(product_id=product.id, product_name=product.name, label=variant.label,
                sku=variant.sku, image_url=found['image_url'], add_quantity=added,
                available_stock=variant.stock, unit_price=str(price),
                original_unit_price=str(found['original_price']) if found['original_price'] is not None else None,
                status='available' if added == requested else 'reduced' if added else 'out_of_stock',
                changes=changes, line_total=str(total))
        items.append(row)
    # Include every existing cart quantity and its live catalog state, even when
    # that SKU is not part of the order being repeated.
    cart_state = [{'variant_id': item.variant_id, 'quantity': item.quantity} for item in cart.items]
    catalog_state = [{'variant_id': key, 'product_id': found['product'].id,
        'name': found['product'].name, 'sku': found['variant'].sku, 'label': found['variant'].label,
        'price': str(found['price']), 'original_price': str(found['original_price']),
        'stock': found['variant'].stock} for key, found in sorted(catalog.items())]
    return {'order_id': order.id, 'fingerprint': digest({'user_id': operations.user_id,
        'order_id': order.id, 'items': items, 'cart': cart_state, 'catalog': catalog_state}),
        'items': items, 'subtotal': str(subtotal), 'currency': 'KZT',
        'can_repeat': any(item['add_quantity'] > 0 for item in items)}


@router.get('/{order_id}/repeat-preview', response_model=RepeatPreview)
def repeat_preview(order_id: OrderId, user: CurrentUser, session: SessionDependency):
    operations = CartOperations(session, user.id)
    operations.lock()
    return _preview(operations, _owned_order(session, user.id, order_id))


@router.post('/{order_id}/repeat', response_model=RepeatResponse)
def repeat_order(order_id: OrderId, data: RepeatRequest, user: CurrentUser, session: SessionDependency):
    operations = CartOperations(session, user.id)
    operations.guard_current_user(data.expected_user_id)
    operations.lock()
    order = _owned_order(session, user.id, order_id)
    body = {'order_id': order_id, 'fingerprint': data.fingerprint, 'expected_user_id': data.expected_user_id}
    replay = operations.replay(data.operation_key, 'repeat', body)
    if replay is not None:
        return replay
    preview = _preview(operations, order)
    if preview['fingerprint'] != data.fingerprint:
        raise HTTPException(409, 'Цены, остатки или корзина изменились. Обновите предварительный просмотр')
    if not preview['can_repeat']:
        raise HTTPException(409, 'В этом заказе нет доступных для добавления товаров')
    cart = operations.cart()
    for item in preview['items']:
        if item['add_quantity']:
            cart.add_item(item['variant_id'], item['add_quantity'])
    operations.repository.save(cart)
    return operations.finish(data.operation_key, 'repeat', body,
        {'cart': operations.service._serialize_cart(cart), 'items': preview['items']})
