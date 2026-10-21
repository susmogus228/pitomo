"""SQLAlchemy ORM models for Petshop API v0.6.0.

The domain objects in ``catalog/models.py``, ``users/models.py`` and other
modules remain framework-agnostic.  These classes represent only persistence.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, event, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class UserORM(Base):
    __tablename__ = 'users'
    __table_args__ = (
        CheckConstraint("role IN ('customer', 'admin')", name='ck_users_role'),
        CheckConstraint('id BETWEEN 1 AND 2147483647', name='ck_users_id_bounds'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default='customer')


class ProductORM(Base):
    __tablename__ = 'products'
    __table_args__ = (
        CheckConstraint("pet_type IN ('cat', 'dog', 'bird', 'small_pet', 'fish', 'reptile', 'amphibian', 'invertebrate')", name='ck_products_pet_type'),
        CheckConstraint("category IN ('food', 'accessory')", name='ck_products_category'),
        CheckConstraint("product_kind IS NULL OR (category = 'food' AND product_kind IN ('food', 'treats')) OR (category = 'accessory' AND product_kind IN ('toys', 'bowls', 'litter', 'habitats', 'walking', 'care', 'aquatics', 'terrariums'))", name='ck_products_kind_category'),
        CheckConstraint('id BETWEEN 1 AND 2147483647', name='ck_products_id_bounds'),
        CheckConstraint('discount_percent IS NULL OR discount_percent BETWEEN 1 AND 90', name='ck_products_discount_percent'),
        CheckConstraint('discount_start_at IS NULL OR discount_end_at IS NULL OR discount_start_at < discount_end_at', name='ck_products_discount_period'),
        Index('ix_products_pet_type_kind', 'pet_type', 'product_kind'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    pet_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    brand: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    brand_normalized: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    product_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    composition: Mapped[str | None] = mapped_column(Text, nullable=True)
    material: Mapped[str | None] = mapped_column(Text, nullable=True)
    discount_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discount_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    discount_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    variants: Mapped[list['ProductVariantORM']] = relationship(
        back_populates='product',
        cascade='all, delete-orphan',
        order_by='ProductVariantORM.id',
        lazy='selectin',
    )


class ProductPhotoORM(Base):
    __tablename__ = 'product_photos'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ConsentReceiptORM(Base):
    __tablename__ = 'consent_receipts'
    __table_args__ = (
        CheckConstraint("purpose IN ('service', 'analytics')", name='ck_consent_receipts_purpose'),
        CheckConstraint("decision IN ('accepted', 'declined', 'withdrawn')", name='ck_consent_receipts_decision'),
        Index('ix_consent_receipts_user_purpose_id', 'user_id', 'purpose', 'id'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    subject_name: Mapped[str] = mapped_column(String(310), nullable=False)
    document: Mapped[str] = mapped_column(Text, nullable=False)
    document_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProductVariantORM(Base):
    __tablename__ = 'product_variants'
    __table_args__ = (
        CheckConstraint('price >= 0', name='ck_product_variants_price_nonnegative'),
        CheckConstraint('stock >= 0', name='ck_product_variants_stock_nonnegative'),
        CheckConstraint('stock <= 2147483647', name='ck_product_variants_stock_max'),
        CheckConstraint('price <= 9999999999.99', name='ck_product_variants_price_max'),
        CheckConstraint('id BETWEEN 1 AND 2147483647', name='ck_product_variants_id_bounds'),
        UniqueConstraint('sku_normalized', name='uq_product_variants_sku_normalized'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True
    )
    sku: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    sku_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default='KZT')
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    product: Mapped[ProductORM] = relationship(back_populates='variants')


class CartORM(Base):
    __tablename__ = 'carts'

    user_id: Mapped[int] = mapped_column(
        ForeignKey('users.id', ondelete='CASCADE'), primary_key=True
    )
    items: Mapped[list['CartItemORM']] = relationship(
        back_populates='cart',
        cascade='all, delete-orphan',
        order_by='CartItemORM.variant_id',
        lazy='selectin',
    )


class CartItemORM(Base):
    __tablename__ = 'cart_items'
    __table_args__ = (
        CheckConstraint('quantity > 0', name='ck_cart_items_quantity_positive'),
        CheckConstraint('quantity <= 10000', name='ck_cart_items_quantity_max'),
        CheckConstraint('variant_id BETWEEN 1 AND 2147483647', name='ck_cart_items_variant_id_bounds'),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey('carts.user_id', ondelete='CASCADE'), primary_key=True
    )
    # Deliberately no FK to product_variants.  v0.4/v0.5 allowed a deleted
    # catalog variant to remain as a stale cart reference until cart read or
    # checkout handles it.  Keeping this soft reference preserves that API
    # behaviour while orders still store a historical snapshot.
    variant_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    cart: Mapped[CartORM] = relationship(back_populates='items')


class SavedAddressORM(Base):
    __tablename__ = 'saved_addresses'
    __table_args__ = (
        CheckConstraint('lat IS NULL OR lat BETWEEN -90 AND 90', name='ck_saved_addresses_lat'),
        CheckConstraint('lon IS NULL OR lon BETWEEN -180 AND 180', name='ck_saved_addresses_lon'),
        CheckConstraint('(lat IS NULL) = (lon IS NULL)', name='ck_saved_addresses_point_pair'),
        CheckConstraint("source IN ('manual', 'geoapify', 'map', 'geolocation')", name='ck_saved_addresses_source'),
        Index('ix_saved_addresses_user_id', 'user_id', 'id'),
        Index('uq_saved_addresses_default', 'user_id', unique=True,
              postgresql_where=text('is_default'), sqlite_where=text('is_default = 1')),
        {'sqlite_autoincrement': True},
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    street: Mapped[str] = mapped_column(String(200), nullable=False)
    house: Mapped[str] = mapped_column(String(40), nullable=False)
    details: Mapped[str] = mapped_column(String(200), nullable=False, default='')
    lat: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    lon: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default='manual')
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CartOperationORM(Base):
    __tablename__ = 'cart_operations'
    __table_args__ = (
        UniqueConstraint('user_id', 'operation_key', name='uq_cart_operations_user_key'),
        CheckConstraint("kind IN ('merge', 'restore', 'favorite', 'repeat')", name='ck_cart_operations_kind'),
        Index('ix_cart_operations_user_created', 'user_id', 'created_at'),
        {'sqlite_autoincrement': True},
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    operation_key: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OrderORM(Base):
    __tablename__ = 'orders'
    __table_args__ = (
        CheckConstraint("status IN ('created', 'cancelled')", name='ck_orders_status_created'),
        CheckConstraint("payment_method IN ('demo', 'cod')", name='ck_orders_payment_method'),
        CheckConstraint("payment_status IN ('pending', 'demo_paid', 'failed', 'cod_pending', 'cancelled')", name='ck_orders_payment_status'),
        CheckConstraint("delivery_method IN ('pickup', 'delivery')", name='ck_orders_delivery_method'),
        CheckConstraint('id BETWEEN 1 AND 2147483647', name='ck_orders_id_bounds'),
        CheckConstraint('delivery_lat IS NULL OR delivery_lat BETWEEN -90 AND 90', name='ck_orders_delivery_lat'),
        CheckConstraint('delivery_lon IS NULL OR delivery_lon BETWEEN -180 AND 180', name='ck_orders_delivery_lon'),
        CheckConstraint('(delivery_lat IS NULL) = (delivery_lon IS NULL)', name='ck_orders_delivery_point_pair'),
        CheckConstraint("delivery_stage IS NULL OR delivery_stage IN ('warehouse', 'in_transit', 'nearby')", name='ck_orders_delivery_stage'),
        CheckConstraint("delivery_incident IS NULL OR delivery_incident IN ('flat_tire', 'overturned', 'engine_failure')", name='ck_orders_delivery_incident'),
        CheckConstraint('delivery_version >= 0', name='ck_orders_delivery_version'),
        UniqueConstraint('user_id', 'idempotency_key', name='uq_orders_user_idempotency_key'),
        Index('ix_orders_user_created_id', 'user_id', 'created_at', 'id'),
        Index('ix_orders_created_sales', 'created_at', 'status', 'payment_status'),
        Index('ix_orders_paid_at', 'paid_at'),
        Index('ix_orders_received_at', 'received_at'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey('users.id', ondelete='RESTRICT'), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default='created')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    checkout_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    delivery_method: Mapped[str] = mapped_column(String(20), nullable=False, default='pickup')
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    comment: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False, default='cod')
    payment_status: Mapped[str] = mapped_column(String(20), nullable=False, default='cod_pending')
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_lat: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    delivery_lon: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    delivery_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    delivery_incident: Mapped[str | None] = mapped_column(String(20), nullable=True)
    delivery_incident_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    delivery_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    delivery_history: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default=text("'[]'"))

    items: Mapped[list['OrderItemORM']] = relationship(
        back_populates='order',
        cascade='all, delete-orphan',
        order_by='OrderItemORM.id',
        lazy='selectin',
    )


class OrderItemORM(Base):
    __tablename__ = 'order_items'
    __table_args__ = (
        CheckConstraint('unit_price >= 0', name='ck_order_items_price_nonnegative'),
        CheckConstraint('quantity > 0', name='ck_order_items_quantity_positive'),
        CheckConstraint('quantity <= 10000', name='ck_order_items_quantity_max'),
        CheckConstraint('unit_price <= 9999999999.99', name='ck_order_items_price_max'),
        CheckConstraint('original_unit_price IS NULL OR original_unit_price >= unit_price', name='ck_order_items_original_price'),
        CheckConstraint('product_id BETWEEN 1 AND 2147483647', name='ck_order_items_product_id_bounds'),
        CheckConstraint('variant_id BETWEEN 1 AND 2147483647', name='ck_order_items_variant_id_bounds'),
        Index('ix_order_items_product_order', 'product_id', 'order_id'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(Integer, nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    variant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    sku: Mapped[str] = mapped_column(String(120), nullable=False)
    variant_label: Mapped[str] = mapped_column(String(120), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    original_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default='KZT')
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    order: Mapped[OrderORM] = relationship(back_populates='items')


class ReviewORM(Base):
    __tablename__ = 'product_reviews'
    __table_args__ = (
        CheckConstraint('rating BETWEEN 1 AND 5', name='ck_product_reviews_rating'),
        UniqueConstraint('user_id', 'product_id', name='uq_product_reviews_user_product'),
        Index('ix_product_reviews_product_created', 'product_id', 'created_at', 'id'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id', ondelete='RESTRICT'), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewReplyORM(Base):
    __tablename__ = 'review_replies'
    __table_args__ = (
        Index('ix_review_replies_review_created', 'review_id', 'created_at', 'id'),
        Index('uq_review_replies_one_official', 'review_id', unique=True,
              postgresql_where=text('is_pinned AND deleted_at IS NULL'),
              sqlite_where=text('is_pinned = 1 AND deleted_at IS NULL')),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(ForeignKey('product_reviews.id', ondelete='CASCADE'), nullable=False)
    parent_reply_id: Mapped[int | None] = mapped_column(ForeignKey('review_replies.id', ondelete='SET NULL'), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    body: Mapped[str] = mapped_column(String(2000), nullable=False)
    is_official: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewReportORM(Base):
    __tablename__ = 'review_reports'
    __table_args__ = (
        UniqueConstraint('reporter_id', 'review_id', name='uq_review_reports_reporter_review'),
        CheckConstraint("reason IN ('spam', 'abuse', 'irrelevant', 'other')", name='ck_review_reports_reason'),
        CheckConstraint("status IN ('pending', 'dismissed', 'actioned')", name='ck_review_reports_status'),
        Index('ix_review_reports_status_created', 'status', 'created_at', 'id'),
        Index('ix_review_reports_review_id', 'review_id'),
        {'sqlite_autoincrement': True},
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(ForeignKey('product_reviews.id', ondelete='CASCADE'), nullable=False)
    reporter_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    details: Mapped[str] = mapped_column(String(500), nullable=False, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='pending')
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True)


class ReviewModerationEventORM(Base):
    __tablename__ = 'review_moderation_events'
    __table_args__ = (
        CheckConstraint("action IN ('hide', 'restore', 'dismiss_reports')", name='ck_review_moderation_events_action'),
        Index('ix_review_moderation_events_review_created', 'review_id', 'created_at', 'id'),
        {'sqlite_autoincrement': True},
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(ForeignKey('product_reviews.id', ondelete='CASCADE'), nullable=False)
    admin_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReviewPhotoORM(Base):
    __tablename__ = 'review_photos'
    __table_args__ = (
        CheckConstraint('(review_id IS NOT NULL) != (reply_id IS NOT NULL)', name='ck_review_photos_one_parent'),
        UniqueConstraint('filename', name='uq_review_photos_filename'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uploader_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    review_id: Mapped[int | None] = mapped_column(ForeignKey('product_reviews.id', ondelete='CASCADE'), nullable=True, index=True)
    reply_id: Mapped[int | None] = mapped_column(ForeignKey('review_replies.id', ondelete='CASCADE'), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StockReplenishmentORM(Base):
    __tablename__ = 'stock_replenishments'
    __table_args__ = (
        CheckConstraint('quantity > 0', name='ck_stock_replenishments_quantity_positive'),
        CheckConstraint('stock_after = stock_before + quantity', name='ck_stock_replenishments_balance'),
        Index('ix_stock_replenishments_variant_created', 'variant_id', 'created_at', 'id'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Historical audit rows stay after a catalog variant is removed.
    variant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    variant_label: Mapped[str] = mapped_column(String(120), nullable=False)
    sku: Mapped[str] = mapped_column(String(120), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    stock_before: Mapped[int] = mapped_column(Integer, nullable=False)
    stock_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IdCounterORM(Base):
    """Committed SQLite identifiers are never allocated again after deletion."""
    __tablename__ = 'id_counters'
    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False)


class BrowserSessionORM(Base):
    __tablename__ = 'browser_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class FavoriteORM(Base):
    __tablename__ = 'favorites'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id', ondelete='CASCADE'), primary_key=True)


@event.listens_for(ProductORM, 'before_insert')
@event.listens_for(ProductORM, 'before_update')
def normalize_product(mapper, connection, target):
    target.name_normalized = target.name.strip().casefold()
    target.brand_normalized = target.brand.strip().casefold()


@event.listens_for(ProductVariantORM, 'before_insert')
@event.listens_for(ProductVariantORM, 'before_update')
def normalize_variant(mapper, connection, target):
    target.sku_normalized = target.sku.strip().casefold()


@event.listens_for(UserORM, 'after_insert')
@event.listens_for(ProductORM, 'after_insert')
@event.listens_for(ProductVariantORM, 'after_insert')
@event.listens_for(OrderORM, 'after_insert')
def remember_sqlite_id(mapper, connection, target):
    if connection.dialect.name == 'sqlite':
        from sqlalchemy.dialects.sqlite import insert
        statement = insert(IdCounterORM).values(name=target.__tablename__, value=target.id)
        connection.execute(statement.on_conflict_do_update(
            index_elements=['name'],
            set_={'value': func.max(IdCounterORM.value, target.id)},
        ))
