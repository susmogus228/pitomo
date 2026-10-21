"""Batched product covers with a gallery fallback for legacy rows."""
from sqlalchemy import func, literal, select

from app.db.models import ProductORM, ProductPhotoORM


def product_images(session, product_ids):
    if not product_ids:
        return {}
    first_photo = (select(ProductPhotoORM.filename)
        .where(ProductPhotoORM.product_id == ProductORM.id)
        .order_by(ProductPhotoORM.created_at, ProductPhotoORM.id)
        .limit(1).correlate(ProductORM).scalar_subquery())
    cover = func.coalesce(func.nullif(ProductORM.image_url, ''),
        literal('/media/products/') + first_photo)
    return dict(session.execute(select(ProductORM.id, cover.label('image_url')).where(
        ProductORM.id.in_(product_ids))).all())
