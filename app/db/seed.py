"""Development/test seed helpers."""
from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.catalog.repository import SQLAlchemyProductRepository
from app.catalog.seed import demo_products

from .models import ProductORM


def seed_demo_catalog(session: Session) -> bool:
    """Insert the original 20 demo products when the catalog is empty.

    Returns ``True`` when rows were inserted and ``False`` when data already
    existed.  It is intentionally idempotent.
    """
    count = int(session.scalar(select(func.count(ProductORM.id))) or 0)
    if count:
        return False
    repository = SQLAlchemyProductRepository(session)
    for product in demo_products():
        repository.add(product)
    if session.get_bind().dialect.name == 'postgresql':
        for table in ('products', 'product_variants'):
            session.execute(text(f"SELECT setval(pg_get_serial_sequence('{table}','id'), (SELECT MAX(id) FROM {table}), true)"))
    return True
