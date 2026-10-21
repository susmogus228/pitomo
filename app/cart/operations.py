"""Atomic, retry-safe additions without replacing existing account cart contents."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json

from fastapi import HTTPException
from sqlalchemy import select

from app.catalog.pricing import active_discount_percent, discounted_price
from app.catalog.repository import SQLAlchemyProductRepository
from app.db.models import CartOperationORM, FavoriteORM, ProductORM, ProductVariantORM

from .models import Cart
from .images import product_images
from .repository import SQLAlchemyCartRepository
from .service import CartService


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


class CartOperations:
    def __init__(self, session, user_id):
        self.session = session
        self.user_id = user_id
        self.repository = SQLAlchemyCartRepository(session)
        self.service = CartService(self.repository, SQLAlchemyProductRepository(session))

    def lock(self):
        self.repository.lock_user(self.user_id)

    def guard_current_user(self, expected_user_id):
        if expected_user_id is not None and expected_user_id != self.user_id:
            raise HTTPException(409, 'Аккаунт изменился. Обновите страницу.')

    def cart(self):
        return self.repository.get_by_user_id(self.user_id) or Cart(self.user_id)

    def replay(self, key, kind, body):
        receipt = self.session.scalar(select(CartOperationORM).where(
            CartOperationORM.user_id == self.user_id, CartOperationORM.operation_key == key))
        if receipt is None:
            return None
        if receipt.kind != kind or receipt.request_hash != digest(body):
            raise HTTPException(409, 'Этот ключ уже использован для другого действия')
        response = deepcopy(receipt.response)
        response['replayed'] = True
        return response

    def finish(self, key, kind, body, response):
        response['replayed'] = False
        self.session.add(CartOperationORM(user_id=self.user_id, operation_key=key, kind=kind,
            request_hash=digest(body), response=response, created_at=datetime.now(timezone.utc)))
        self.session.flush()
        return response

    def catalog(self, variant_ids):
        if not variant_ids:
            return {}
        # Catalog writes take product then SKU locks. Keep the same order.
        product_ids = list(self.session.scalars(select(ProductVariantORM.product_id).where(
            ProductVariantORM.id.in_(variant_ids)).distinct().order_by(ProductVariantORM.product_id)))
        if product_ids:
            self.session.execute(select(ProductORM.id).where(ProductORM.id.in_(product_ids))
                .order_by(ProductORM.id).with_for_update()).all()
        rows = self.session.execute(select(ProductVariantORM, ProductORM)
            .join(ProductORM, ProductORM.id == ProductVariantORM.product_id)
            .where(ProductVariantORM.id.in_(variant_ids)).order_by(ProductVariantORM.id)
            .with_for_update(of=ProductVariantORM).execution_options(populate_existing=True)).all()
        now = datetime.now(timezone.utc)
        results = {}
        images = product_images(self.session, product_ids)
        for variant, product in rows:
            percent = active_discount_percent(product.discount_percent, product.discount_start_at,
                product.discount_end_at, now)
            results[variant.id] = {'variant': variant, 'product': product,
                'image_url': images.get(product.id),
                'price': discounted_price(variant.price, percent),
                'original_price': variant.price if percent is not None else None}
        return results

    @staticmethod
    def allowed(cart, variant_id, requested, stock):
        existing = cart.get_item(variant_id)
        quantity = existing.quantity if existing else 0
        return min(requested, max(0, min(stock, 10000) - quantity))

    def additions(self, key, kind, items, expected_user_id=None):
        self.guard_current_user(expected_user_id)
        self.lock()
        body = {'items': items, 'expected_user_id': expected_user_id}
        replay = self.replay(key, kind, body)
        if replay is not None:
            return replay
        cart = self.cart()
        catalog = self.catalog([item['variant_id'] for item in items])
        results = []
        for item in items:
            variant_id, requested = item['variant_id'], item['quantity']
            found = catalog.get(variant_id)
            added = self.allowed(cart, variant_id, requested, found['variant'].stock) if found else 0
            status = 'missing' if found is None else (
                'added' if added == requested else 'reduced' if added else 'out_of_stock')
            messages = {'missing': 'Вариант товара удалён из каталога', 'added': 'Добавлено в корзину',
                'reduced': 'Добавлено доступное количество с учётом корзины и остатка',
                'out_of_stock': 'Нет доступного количества сверх уже добавленного в корзину'}
            if added:
                cart.add_item(variant_id, added)
            results.append({'variant_id': variant_id, 'requested_quantity': requested,
                'added_quantity': added, 'remaining_quantity': requested - added,
                'status': status, 'message': messages[status]})
        self.repository.save(cart)
        return self.finish(key, kind, body, {'cart': self.service._serialize_cart(cart), 'items': results})

    def favorite(self, key, variant_id, expected_user_id=None):
        self.guard_current_user(expected_user_id)
        self.lock()
        body = {'variant_id': variant_id, 'expected_user_id': expected_user_id}
        replay = self.replay(key, 'favorite', body)
        if replay is not None:
            return replay
        cart = self.cart()
        if cart.get_item(variant_id) is None:
            raise HTTPException(404, 'Позиция не найдена в корзине')
        found = self.catalog([variant_id]).get(variant_id)
        if found is None:
            raise HTTPException(409, 'Товар удалён; перенос в избранное невозможен')
        product_id = found['product'].id
        if self.session.get(FavoriteORM, (self.user_id, product_id)) is None:
            self.session.add(FavoriteORM(user_id=self.user_id, product_id=product_id))
        cart.remove_item(variant_id)
        self.repository.save(cart)
        return self.finish(key, 'favorite', body,
            {'cart': self.service._serialize_cart(cart), 'product_id': product_id})
