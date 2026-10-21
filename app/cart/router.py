"""Protected HTTP routes for the current user's shopping cart."""
from __future__ import annotations

from typing import Annotated

from fastapi import Path, APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.core.schemas import ErrorResponse
from app.db.dependencies import get_db_session
from app.catalog.repository import SQLAlchemyProductRepository

from .schemas import (CartItemCreate, CartItemUpdate, CartResponse, CartFavoriteResponse,
    CartMergeRequest, CartMutationResponse, CartOperationRequest, CartRestoreRequest)
from app.db.dependencies import SessionDependency
from .operations import CartOperations
from .repository import SQLAlchemyCartRepository
from .service import CartService

router = APIRouter(prefix='/api/v1/cart', tags=['Корзина'])


def get_cart_service(
    session: Annotated[Session, Depends(get_db_session, scope="function")],
) -> CartService:
    return CartService(
        SQLAlchemyCartRepository(session),
        SQLAlchemyProductRepository(session),
    )


CartServiceDependency = Annotated[CartService, Depends(get_cart_service)]

AUTH_ERROR = {401: {'model': ErrorResponse, 'description': 'Bearer-токен отсутствует или недействителен'}}


@router.post('/merge', response_model=CartMutationResponse, summary='Объединить гостевую корзину с аккаунтом')
def merge_cart(data: CartMergeRequest, current_user: CurrentUser, session: SessionDependency):
    return CartOperations(session, current_user.id).additions(data.operation_key, 'merge',
        [item.model_dump() for item in data.items], data.expected_user_id)


@router.post('/items/restore', response_model=CartMutationResponse, summary='Вернуть удалённое доступное количество')
def restore_cart_item(data: CartRestoreRequest, current_user: CurrentUser, session: SessionDependency):
    return CartOperations(session, current_user.id).additions(data.operation_key, 'restore',
        [{'variant_id': data.variant_id, 'quantity': data.quantity}], data.expected_user_id)


@router.post('/items/{variant_id}/favorite', response_model=CartFavoriteResponse,
             summary='Атомарно перенести позицию из корзины в избранное')
def favorite_cart_item(variant_id: Annotated[int, Path(gt=0, le=2147483647)],
                      data: CartOperationRequest, current_user: CurrentUser, session: SessionDependency):
    return CartOperations(session, current_user.id).favorite(data.operation_key, variant_id, data.expected_user_id)


@router.get(
    '',
    response_model=CartResponse,
    summary='Получить свою корзину',
    responses=AUTH_ERROR,
)
def current_cart(current_user: CurrentUser, service: CartServiceDependency):
    return service.get_cart(current_user.id)


@router.post(
    '/items',
    response_model=CartResponse,
    summary='Добавить вариант товара в корзину',
    responses={
        **AUTH_ERROR,
        404: {'model': ErrorResponse, 'description': 'Вариант товара не найден'},
        409: {'model': ErrorResponse, 'description': 'Недостаточный остаток'},
        422: {'model': ErrorResponse, 'description': 'Некорректные данные позиции'},
    },
)
def add_cart_item(
    data: CartItemCreate,
    current_user: CurrentUser,
    service: CartServiceDependency,
):
    return service.add_item(current_user.id, data.variant_id, data.quantity)


@router.patch(
    '/items/{variant_id}',
    response_model=CartResponse,
    summary='Изменить количество позиции',
    responses={
        **AUTH_ERROR,
        404: {'model': ErrorResponse, 'description': 'Позиция корзины или вариант товара не найден'},
        409: {'model': ErrorResponse, 'description': 'Недостаточный остаток'},
        422: {'model': ErrorResponse, 'description': 'Некорректное количество'},
    },
)
def update_cart_item(
    variant_id: Annotated[int, Path(gt=0, le=2147483647)],
    data: CartItemUpdate,
    current_user: CurrentUser,
    service: CartServiceDependency,
):
    return service.update_item(current_user.id, variant_id, data.quantity)


@router.delete(
    '/items/{variant_id}',
    status_code=status.HTTP_204_NO_CONTENT,
    summary='Удалить позицию из корзины',
    responses={
        **AUTH_ERROR,
        404: {'model': ErrorResponse, 'description': 'Позиция не найдена в корзине'},
    },
)
def delete_cart_item(
    variant_id: Annotated[int, Path(gt=0, le=2147483647)],
    current_user: CurrentUser,
    service: CartServiceDependency,
):
    service.remove_item(current_user.id, variant_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    '',
    status_code=status.HTTP_204_NO_CONTENT,
    summary='Очистить свою корзину',
    responses=AUTH_ERROR,
)
def clear_cart(current_user: CurrentUser, service: CartServiceDependency):
    service.clear_cart(current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
