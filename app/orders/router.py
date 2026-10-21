"""Protected HTTP routes for the current user's orders."""
from __future__ import annotations

from typing import Annotated

from fastapi import Header, Query, Path, APIRouter, Depends, status, Request
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.core.schemas import ErrorResponse
from app.db.dependencies import get_db_session
from app.catalog.repository import SQLAlchemyProductRepository
from app.cart.repository import SQLAlchemyCartRepository

from .schemas import OrderResponse, CheckoutRequest, DemoPaymentRequest
from .repository import SQLAlchemyOrderRepository
from .service import OrderService

router = APIRouter(prefix='/api/v1/orders', tags=['Заказы'])


def get_order_service(
    session: Annotated[Session, Depends(get_db_session, scope="function")],
) -> OrderService:
    return OrderService(
        SQLAlchemyOrderRepository(session),
        SQLAlchemyCartRepository(session),
        SQLAlchemyProductRepository(session),
    )


OrderServiceDependency = Annotated[OrderService, Depends(get_order_service)]

AUTH_ERROR = {401: {'model': ErrorResponse, 'description': 'Bearer-токен отсутствует или недействителен'}}


@router.post(
    '',
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary='Оформить заказ из текущей корзины',
    responses={
        **AUTH_ERROR,
        409: {
            'model': ErrorResponse,
            'description': 'Корзина пуста, товар удалён или текущего остатка недостаточно',
        },
        422: {'model': ErrorResponse, 'description': 'Нарушены инварианты данных заказа'},
    },
)
def checkout(current_user: CurrentUser, service: OrderServiceDependency, request: Request,
             data: CheckoutRequest | None = None,
             idempotency_key: Annotated[str | None, Header(min_length=1, max_length=128)] = None):
    return service.checkout(current_user.id, idempotency_key=idempotency_key, details=data,
                            demo_enabled=request.app.state.settings.demo_payments_enabled)


@router.post('/{order_id}/demo-payment', response_model=OrderResponse, summary='Тестовая оплата без списания денег')
def demo_payment(order_id: Annotated[int, Path(gt=0, le=2147483647)], data: DemoPaymentRequest,
                 current_user: CurrentUser, service: OrderServiceDependency, request: Request):
    return service.demo_payment(current_user.id, order_id, data.outcome,
                                enabled=request.app.state.settings.demo_payments_enabled)


@router.post('/{order_id}/cancel', response_model=OrderResponse, summary='Отменить неоплаченный заказ')
def cancel_order(order_id: Annotated[int, Path(gt=0, le=2147483647)], current_user: CurrentUser,
                 service: OrderServiceDependency):
    return service.cancel(current_user.id, order_id)


@router.post('/{order_id}/confirm-receipt', response_model=OrderResponse,
             summary='Подтвердить получение своего заказа')
def confirm_receipt(order_id: Annotated[int, Path(gt=0, le=2147483647)],
                    current_user: CurrentUser, service: OrderServiceDependency):
    return service.confirm_receipt(current_user.id, order_id)


@router.get(
    '',
    response_model=list[OrderResponse],
    summary='Получить историю своих заказов',
    responses=AUTH_ERROR,
)
def list_orders(current_user: CurrentUser, service: OrderServiceDependency,
                limit: Annotated[int, Query(ge=1, le=100)] = 50,
                offset: Annotated[int, Query(ge=0, le=2147483647)] = 0):
    return service.list_orders(current_user.id, limit=limit, offset=offset)


@router.get(
    '/{order_id}',
    response_model=OrderResponse,
    summary='Получить свой заказ по ID',
    responses={
        **AUTH_ERROR,
        404: {'model': ErrorResponse, 'description': 'Заказ не найден у текущего пользователя'},
        422: {'model': ErrorResponse, 'description': 'Некорректный order_id'},
    },
)
def get_order(order_id: Annotated[int, Path(gt=0, le=2147483647)], current_user: CurrentUser, service: OrderServiceDependency):
    return service.get_order(current_user.id, order_id)
