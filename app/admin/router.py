"""Admin-only HTTP API."""
from __future__ import annotations

from typing import Annotated, Literal
from datetime import datetime, timezone

from fastapi import Query, Path, APIRouter, Depends, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import func, select, update, exists
from sqlalchemy.orm import selectinload

from app.auth.dependencies import AdminUser
from app.core.schemas import ErrorResponse
from app.db.dependencies import get_db_session
from app.db.dependencies import SessionDependency
from app.catalog.schemas import DiscountRequest, ProductResponse, ProductPage
from app.catalog.repository import SQLAlchemyProductRepository
from app.catalog.service import CatalogService
from app.users.repository import SQLAlchemyUserRepository
from app.users.schemas import UserResponse
from app.db.models import OrderORM, UserORM, ProductORM, ProductVariantORM, ReviewORM, ReviewReplyORM, StockReplenishmentORM
from app.db.mappers import order_to_domain
from app.orders.service import OrderService
from app.orders.exceptions import OrderNotFoundError
from app.orders.schemas import DeliveryUpdateRequest
from app.orders.router import OrderServiceDependency

from .schemas import AdminUserUpdate, AdminOrderResponse, AdminOrderPage, AdminUserPage
from .order_filters import (
    DeliveryStageFilter, DeliveryIncidentFilter, OrderQueue, ORDER_QUEUES, order_criteria,
)
from .service import AdminService
from pydantic import BaseModel, ConfigDict, Field
from fastapi import HTTPException

router = APIRouter(prefix='/api/v1/admin', tags=['Администрирование'])


def get_admin_service(
    session: Annotated[Session, Depends(get_db_session, scope="function")],
) -> AdminService:
    return AdminService(SQLAlchemyUserRepository(session))


AdminServiceDependency = Annotated[AdminService, Depends(get_admin_service)]

_COMMON_RESPONSES = {
    401: {'model': ErrorResponse, 'description': 'Bearer-токен отсутствует или недействителен'},
    403: {'model': ErrorResponse, 'description': 'Требуются права администратора'},
}


class ReplenishmentCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    quantity: int = Field(gt=0, le=100000)
    reason: str = Field(min_length=3, max_length=300)


class ReplenishmentResponse(BaseModel):
    id: int
    variant_id: int
    product_name: str
    variant_label: str
    sku: str
    quantity: int
    stock_before: int
    stock_after: int
    reason: str
    created_at: datetime
    actor_id: int | None


@router.get('/dashboard', summary='Сводка магазина', responses=_COMMON_RESPONSES)
def dashboard(admin_user: AdminUser, session: SessionDependency):
    unanswered = ~exists(select(ReviewReplyORM.id).where(
        ReviewReplyORM.review_id == ReviewORM.id,
        ReviewReplyORM.is_pinned.is_(True), ReviewReplyORM.deleted_at.is_(None)))
    queues = {queue: session.scalar(select(func.count(OrderORM.id)).where(
        *order_criteria(queue=queue))) or 0 for queue in ORDER_QUEUES}
    return {
        'orders_total': session.scalar(select(func.count(OrderORM.id))) or 0,
        'orders_pending': queues['active'],
        'order_queues': queues,
        'products_total': session.scalar(select(func.count(ProductORM.id))) or 0,
        'low_stock_variants': session.scalar(select(func.count(ProductVariantORM.id)).where(
            ProductVariantORM.stock <= 5)) or 0,
        'low_stock_products': session.scalar(select(func.count(func.distinct(
            ProductVariantORM.product_id))).where(ProductVariantORM.stock <= 5)) or 0,
        'reviews_total': session.scalar(select(func.count(ReviewORM.id)).where(
            ReviewORM.deleted_at.is_(None))) or 0,
        'unanswered_reviews': session.scalar(select(func.count(ReviewORM.id)).where(
            ReviewORM.deleted_at.is_(None), unanswered)) or 0,
    }


@router.get('/reviews', summary='Очередь отзывов', responses=_COMMON_RESPONSES)
def admin_reviews(admin_user: AdminUser, session: SessionDependency,
                  unanswered_only: bool = False,
                  visibility: Literal['all', 'visible', 'hidden'] = 'all',
                  limit: Annotated[int, Query(ge=1, le=100)] = 50,
                  offset: Annotated[int, Query(ge=0, le=2147483647)] = 0):
    answered = exists(select(ReviewReplyORM.id).where(
        ReviewReplyORM.review_id == ReviewORM.id,
        ReviewReplyORM.is_pinned.is_(True), ReviewReplyORM.deleted_at.is_(None)))
    filters = [ReviewORM.deleted_at.is_(None)]
    if visibility != 'all':
        filters.append(ReviewORM.hidden_at.is_(None) if visibility == 'visible' else ReviewORM.hidden_at.is_not(None))
    if unanswered_only:
        filters.append(~answered)
    total = session.scalar(select(func.count(ReviewORM.id)).where(*filters)) or 0
    rows = session.execute(select(ReviewORM, ProductORM.name, UserORM.first_name, answered.label('answered'))
                           .join(ProductORM, ProductORM.id == ReviewORM.product_id)
                           .join(UserORM, UserORM.id == ReviewORM.user_id)
                           .where(*filters).order_by(ReviewORM.created_at.desc(), ReviewORM.id.desc())
                           .limit(limit).offset(offset)).all()
    return {'items': [{'id': row.id, 'product_id': row.product_id, 'product_name': product_name,
                       'author_name': author_name, 'rating': row.rating, 'body': row.body,
                       'created_at': row.created_at, 'is_hidden': row.hidden_at is not None,
                       'is_edited': row.edited_at is not None,
                       'replies_count': session.scalar(select(func.count(ReviewReplyORM.id)).where(
                           ReviewReplyORM.review_id == row.id, ReviewReplyORM.deleted_at.is_(None))) or 0,
                       'has_official_reply': bool(is_answered)}
                      for row, product_name, author_name, is_answered in rows],
            'total': total, 'limit': limit, 'offset': offset}


@router.post('/variants/{variant_id}/replenishments', response_model=ReplenishmentResponse,
             status_code=201, summary='Добавить товар на склад', responses=_COMMON_RESPONSES)
def replenish_variant(variant_id: Annotated[int, Path(gt=0, le=2147483647)],
                      data: ReplenishmentCreate, admin_user: AdminUser,
                      session: SessionDependency):
    # One atomic UPDATE prevents lost increments under simultaneous administrators.
    stock_after = session.scalar(update(ProductVariantORM)
        .where(ProductVariantORM.id == variant_id,
               ProductVariantORM.stock <= 2147483647 - data.quantity)
        .values(stock=ProductVariantORM.stock + data.quantity)
        .returning(ProductVariantORM.stock))
    if stock_after is None:
        if session.get(ProductVariantORM, variant_id) is None:
            raise HTTPException(404, 'Вариант товара не найден')
        raise HTTPException(409, 'Превышен допустимый остаток')
    variant = session.get(ProductVariantORM, variant_id)
    product = session.get(ProductORM, variant.product_id)
    row = StockReplenishmentORM(variant_id=variant_id, actor_id=admin_user.id,
                                product_name=product.name, variant_label=variant.label,
                                sku=variant.sku,
                                quantity=data.quantity, stock_before=stock_after - data.quantity,
                                stock_after=stock_after, reason=data.reason,
                                created_at=datetime.now(timezone.utc))
    session.add(row)
    session.flush()
    return row


@router.get('/replenishments', summary='История пополнений', responses=_COMMON_RESPONSES)
def list_replenishments(admin_user: AdminUser, session: SessionDependency,
                        variant_id: Annotated[int | None, Query(gt=0, le=2147483647)] = None,
                        limit: Annotated[int, Query(ge=1, le=100)] = 50,
                        offset: Annotated[int, Query(ge=0, le=2147483647)] = 0):
    filters = [StockReplenishmentORM.variant_id == variant_id] if variant_id is not None else []
    total = session.scalar(select(func.count(StockReplenishmentORM.id)).where(*filters)) or 0
    rows = session.scalars(select(StockReplenishmentORM).where(*filters)
                           .order_by(StockReplenishmentORM.created_at.desc(), StockReplenishmentORM.id.desc())
                           .limit(limit).offset(offset)).all()
    return {'items': [ReplenishmentResponse.model_validate(row, from_attributes=True).model_dump()
                      for row in rows], 'total': total, 'limit': limit, 'offset': offset}


@router.get(
    '/users',
    response_model=list[UserResponse],
    summary='Список пользователей',
    responses=_COMMON_RESPONSES,
)
def list_users(admin_user: AdminUser, service: AdminServiceDependency,
               limit: Annotated[int, Query(ge=1, le=100)] = 50,
               offset: Annotated[int, Query(ge=0, le=2147483647)] = 0):
    return [user.to_dict() for user in service.list_users(limit=limit, offset=offset)]


@router.get('/users/page', response_model=AdminUserPage,
            summary='Страница пользователей с общим количеством', responses=_COMMON_RESPONSES)
def list_user_page(admin_user: AdminUser, service: AdminServiceDependency,
                   session: SessionDependency,
                   limit: Annotated[int, Query(ge=1, le=100)] = 50,
                   offset: Annotated[int, Query(ge=0, le=2147483647)] = 0):
    return {'items': [user.to_dict() for user in service.list_users(limit=limit, offset=offset)],
            'total': session.scalar(select(func.count(UserORM.id))) or 0,
            'limit': limit, 'offset': offset}


@router.get('/products', response_model=ProductPage,
            summary='Товары для администратора с фильтром малого остатка', responses=_COMMON_RESPONSES)
def list_admin_products(admin_user: AdminUser, session: SessionDependency,
                        q: Annotated[str | None, Query(max_length=100)] = None,
                        stock_max: Annotated[int | None, Query(ge=0, le=2147483647)] = None,
                        page: Annotated[int, Query(ge=1, le=2147483647)] = 1,
                        page_size: Annotated[int, Query(ge=1, le=100)] = 20):
    from app.catalog.router import _with_ratings
    result = SQLAlchemyProductRepository(session).query_page(
        q=q, stock_max=stock_max, page=page, page_size=page_size)
    _with_ratings(result['items'], session)
    return result


@router.get(
    '/users/{user_id}',
    response_model=UserResponse,
    summary='Получить пользователя',
    responses={
        **_COMMON_RESPONSES,
        404: {'model': ErrorResponse, 'description': 'Пользователь не найден'},
    },
)
def get_user(user_id: Annotated[int, Path(gt=0, le=2147483647)], admin_user: AdminUser, service: AdminServiceDependency):
    return service.get_user(user_id).to_dict()


@router.patch(
    '/users/{user_id}',
    response_model=UserResponse,
    summary='Изменить роль или активность пользователя',
    responses={
        **_COMMON_RESPONSES,
        404: {'model': ErrorResponse, 'description': 'Пользователь не найден'},
        409: {'model': ErrorResponse, 'description': 'Попытка заблокировать собственный admin-доступ'},
        422: {'model': ErrorResponse, 'description': 'Некорректные данные'},
    },
)
def update_user(
    user_id: Annotated[int, Path(gt=0, le=2147483647)],
    data: AdminUserUpdate,
    admin_user: AdminUser,
    service: AdminServiceDependency,
):
    return service.update_user(admin_user, user_id, data).to_dict()


@router.put('/products/{product_id}/discount', response_model=ProductResponse,
            summary='Задать процент и период скидки для товара', responses=_COMMON_RESPONSES)
def set_product_discount(product_id: Annotated[int, Path(gt=0, le=2147483647)],
                         data: DiscountRequest, admin_user: AdminUser,
                         session: SessionDependency):
    service = CatalogService(SQLAlchemyProductRepository(session))
    from app.catalog.router import _with_ratings
    return _with_ratings([service.set_discount(product_id, data).to_dict()], session)[0]


@router.delete('/products/{product_id}/discount', status_code=status.HTTP_204_NO_CONTENT,
               summary='Удалить скидку товара', responses=_COMMON_RESPONSES)
def clear_product_discount(product_id: Annotated[int, Path(gt=0, le=2147483647)],
                           admin_user: AdminUser, session: SessionDependency):
    service = CatalogService(SQLAlchemyProductRepository(session))
    service.clear_discount(product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _admin_order_payload(row: OrderORM, email: str, first_name: str) -> dict:
    return {**OrderService._serialize_order(order_to_domain(row)),
            'customer_email': email, 'customer_first_name': first_name}


@router.get('/orders', response_model=AdminOrderPage,
            summary='Список заказов для оператора', responses=_COMMON_RESPONSES)
def list_admin_orders(admin_user: AdminUser, session: SessionDependency,
                      limit: Annotated[int, Query(ge=1, le=100)] = 50,
                      offset: Annotated[int, Query(ge=0, le=2147483647)] = 0,
                      status_filter: Annotated[Literal['created', 'cancelled'] | None,
                                               Query(alias='status')] = None,
                      payment_status: Literal['pending', 'demo_paid', 'failed', 'cod_pending', 'cancelled'] | None = None,
                      delivery_method: Literal['pickup', 'delivery'] | None = None,
                      user_id: Annotated[int | None, Query(gt=0, le=2147483647)] = None,
                      delivery_stage: DeliveryStageFilter | None = None,
                      delivery_incident: DeliveryIncidentFilter | None = None,
                      received: bool | None = None,
                      stale_hours: Annotated[int | None, Query(ge=1, le=8760)] = None,
                      queue: OrderQueue | None = None):
    criteria = order_criteria(status=status_filter, payment_status=payment_status,
        delivery_method=delivery_method, user_id=user_id, delivery_stage=delivery_stage,
        delivery_incident=delivery_incident, received=received, stale_hours=stale_hours, queue=queue)
    total = session.scalar(select(func.count(OrderORM.id)).where(*criteria)) or 0
    rows = session.execute(
        select(OrderORM, UserORM.email, UserORM.first_name)
        .join(UserORM, UserORM.id == OrderORM.user_id)
        .where(*criteria).options(selectinload(OrderORM.items))
        .order_by(OrderORM.created_at.desc(), OrderORM.id.desc())
        .limit(limit).offset(offset)
    ).all()
    return {'items': [_admin_order_payload(row, email, first_name)
                      for row, email, first_name in rows],
            'total': total, 'limit': limit, 'offset': offset}


@router.get('/orders/{order_id}', response_model=AdminOrderResponse,
            summary='Просмотреть заказ и точку доставки',
            responses={**_COMMON_RESPONSES, 404: {'model': ErrorResponse, 'description': 'Заказ не найден'}})
def get_admin_order(order_id: Annotated[int, Path(gt=0, le=2147483647)],
                    admin_user: AdminUser, session: SessionDependency):
    row = session.execute(
        select(OrderORM, UserORM.email, UserORM.first_name)
        .join(UserORM, UserORM.id == OrderORM.user_id)
        .where(OrderORM.id == order_id).options(selectinload(OrderORM.items))
    ).one_or_none()
    if row is None:
        raise OrderNotFoundError('Заказ не найден')
    return _admin_order_payload(*row)


@router.patch('/orders/{order_id}/delivery', response_model=AdminOrderResponse,
              summary='Обновить этап доставки или поломку',
              responses={**_COMMON_RESPONSES,
                         404: {'model': ErrorResponse, 'description': 'Заказ не найден'},
                         409: {'model': ErrorResponse, 'description': 'Устаревшая версия или недопустимый переход'}})
def update_admin_delivery(order_id: Annotated[int, Path(gt=0, le=2147483647)],
                          data: DeliveryUpdateRequest, admin_user: AdminUser,
                          service: OrderServiceDependency, session: SessionDependency):
    payload = service.update_delivery(order_id, data)
    customer = session.get(UserORM, payload['user_id'])
    return {**payload, 'customer_email': customer.email,
            'customer_first_name': customer.first_name}
