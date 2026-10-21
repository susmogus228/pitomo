"""Idempotent authenticated favorite operations."""
from typing import Annotated

from fastapi import APIRouter, Path, Response
from sqlalchemy import delete, select

from app.auth.dependencies import CurrentUser
from app.cart.repository import SQLAlchemyCartRepository
from app.catalog.exceptions import ProductNotFoundError
from app.catalog.schemas import ProductResponse
from app.db.dependencies import SessionDependency
from app.db.mappers import product_to_domain
from app.db.models import FavoriteORM, ProductORM

router = APIRouter(prefix='/api/v1/favorites', tags=['Избранное'])
ProductId = Annotated[int, Path(gt=0, le=2147483647)]


@router.get('', response_model=list[ProductResponse])
def favorites(user: CurrentUser, session: SessionDependency):
    products = session.scalars(select(ProductORM).join(FavoriteORM).where(
        FavoriteORM.user_id == user.id).order_by(ProductORM.id)).all()
    return [product_to_domain(product).to_dict() for product in products]


@router.put('/{product_id}', status_code=204)
def add_favorite(product_id: ProductId, user: CurrentUser, session: SessionDependency):
    SQLAlchemyCartRepository(session).lock_user(user.id)
    if session.scalar(select(ProductORM.id).where(ProductORM.id == product_id).with_for_update()) is None:
        raise ProductNotFoundError('Товар не найден')
    if session.get(FavoriteORM, (user.id, product_id)) is None:
        session.add(FavoriteORM(user_id=user.id, product_id=product_id))
    return Response(status_code=204)


@router.delete('/{product_id}', status_code=204)
def remove_favorite(product_id: ProductId, user: CurrentUser, session: SessionDependency):
    SQLAlchemyCartRepository(session).lock_user(user.id)
    session.execute(delete(FavoriteORM).where(
        FavoriteORM.user_id == user.id, FavoriteORM.product_id == product_id))
    return Response(status_code=204)
