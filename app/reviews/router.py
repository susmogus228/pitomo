"""Public review listing and purchase-verified review creation."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.catalog.exceptions import ProductNotFoundError
from app.db.dependencies import get_db_session
from app.db.models import OrderItemORM, OrderORM, ProductORM, ReviewORM, ReviewPhotoORM, UserORM
from app.orders.exceptions import OrderCheckoutError, OrderNotFoundError
from .schemas import ReviewCreate, ReviewResponse, ReviewPage
from .serialization import review_payload

router = APIRouter(prefix='/api/v1/products/{product_id}/reviews', tags=['Отзывы'])
DbSession = Annotated[Session, Depends(get_db_session, scope='function')]
ProductId = Annotated[int, Path(gt=0, le=2147483647)]


def _assert_product(session: Session, product_id: int) -> None:
    if session.get(ProductORM, product_id) is None:
        raise ProductNotFoundError('Товар не найден')


@router.get('', response_model=ReviewPage, summary='Публичные отзывы о товаре')
def list_reviews(product_id: ProductId, session: DbSession,
                 limit: Annotated[int, Query(ge=1, le=100)] = 5,
                 offset: Annotated[int, Query(ge=0, le=2147483647)] = 0,
                 sort: Literal['newest', 'oldest', 'rating_desc', 'rating_asc'] = 'newest',
                 with_photos: bool = False,
                 rating: Annotated[int | None, Query(ge=1, le=5)] = None):
    _assert_product(session, product_id)
    visible = [ReviewORM.product_id == product_id, ReviewORM.deleted_at.is_(None), ReviewORM.hidden_at.is_(None)]
    distribution = {str(stars): 0 for stars in range(1, 6)}
    for stars, count in session.execute(select(ReviewORM.rating, func.count(ReviewORM.id))
                                        .where(*visible).group_by(ReviewORM.rating)):
        distribution[str(stars)] = count
    summary_total = sum(distribution.values())
    average = sum(int(stars) * count for stars, count in distribution.items()) / summary_total if summary_total else None
    filters = list(visible)
    if with_photos:
        filters.append(select(ReviewPhotoORM.id).where(ReviewPhotoORM.review_id == ReviewORM.id,
                                                       ReviewPhotoORM.deleted_at.is_(None)).exists())
    if rating is not None:
        filters.append(ReviewORM.rating == rating)
    total = session.scalar(select(func.count(ReviewORM.id)).where(*filters)) or 0
    ordering = {
        'newest': (ReviewORM.created_at.desc(), ReviewORM.id.desc()),
        'oldest': (ReviewORM.created_at.asc(), ReviewORM.id.asc()),
        'rating_desc': (ReviewORM.rating.desc(), ReviewORM.created_at.desc(), ReviewORM.id.desc()),
        'rating_asc': (ReviewORM.rating.asc(), ReviewORM.created_at.desc(), ReviewORM.id.desc()),
    }[sort]
    rows = session.execute(
        select(ReviewORM, UserORM.first_name).join(UserORM, UserORM.id == ReviewORM.user_id)
        .where(*filters)
        .order_by(*ordering)
        .limit(limit).offset(offset)
    ).all()
    return {'items': [review_payload(session, review, first_name)
                      for review, first_name in rows],
            'total': total, 'average_rating': round(float(average), 2) if average is not None else None,
            'summary_total': summary_total, 'rating_distribution': distribution}


@router.get('/mine', response_model=ReviewResponse | None, summary='Свой отзыв и состояние модерации')
def own_review(product_id: ProductId, current_user: CurrentUser, session: DbSession):
    _assert_product(session, product_id)
    row = session.scalar(select(ReviewORM).where(ReviewORM.product_id == product_id,
        ReviewORM.user_id == current_user.id, ReviewORM.deleted_at.is_(None)))
    return review_payload(session, row, current_user.first_name) if row is not None else None


@router.post('', response_model=ReviewResponse, status_code=status.HTTP_201_CREATED,
             summary='Оставить отзыв после подтверждения получения заказа')
def create_review(product_id: ProductId, data: ReviewCreate,
                  current_user: CurrentUser, session: DbSession):
    _assert_product(session, product_id)
    order = session.scalar(select(OrderORM).where(OrderORM.id == data.order_id,
                                                  OrderORM.user_id == current_user.id).with_for_update())
    if order is None:
        raise OrderNotFoundError('Заказ не найден')
    if order.status != 'created' or order.received_at is None:
        raise OrderCheckoutError('Отзыв доступен после подтверждения получения товара')
    item = session.scalar(select(OrderItemORM.id).where(OrderItemORM.order_id == data.order_id,
                                                       OrderItemORM.product_id == product_id).limit(1))
    if item is None:
        raise OrderCheckoutError('Товара нет в указанном заказе')
    existing = session.scalar(select(ReviewORM).where(ReviewORM.user_id == current_user.id,
                                                      ReviewORM.product_id == product_id).with_for_update())
    if existing is not None and existing.hidden_at is not None:
        raise HTTPException(409, 'Отзыв скрыт администратором. Повторная публикация недоступна.')
    if existing is not None and existing.deleted_at is None:
        raise OrderCheckoutError('Вы уже оставили отзыв на этот товар')
    now = datetime.now(timezone.utc)
    if existing is None:
        review = ReviewORM(product_id=product_id, user_id=current_user.id, order_id=order.id,
                           rating=data.rating, body=data.body, created_at=now, updated_at=now)
        session.add(review)
    else:
        review = existing
        review.order_id = order.id
        review.rating = data.rating
        review.body = data.body
        review.deleted_at = None
        review.edited_at = None
        review.created_at = now
        review.updated_at = now
    session.flush()
    return review_payload(session, review, current_user.first_name)
