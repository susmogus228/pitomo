"""Protected HTTP routes for the current user profile."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.core.schemas import ErrorResponse
from app.db.dependencies import get_db_session

from .schemas import UserResponse, UserUpdate
from .repository import SQLAlchemyUserRepository
from .service import UserService

router = APIRouter(prefix='/api/v1/users', tags=['Пользователи'])


def get_user_service(
    session: Annotated[Session, Depends(get_db_session, scope="function")],
) -> UserService:
    return UserService(SQLAlchemyUserRepository(session))


UserServiceDependency = Annotated[UserService, Depends(get_user_service)]


@router.get(
    '/me',
    response_model=UserResponse,
    summary='Текущий пользователь',
    responses={401: {'model': ErrorResponse, 'description': 'Bearer-токен отсутствует или недействителен'}},
)
def current_profile(current_user: CurrentUser):
    return current_user.to_dict()


@router.patch(
    '/me',
    response_model=UserResponse,
    summary='Изменить свой профиль',
    responses={
        401: {'model': ErrorResponse, 'description': 'Bearer-токен отсутствует или недействителен'},
        409: {'model': ErrorResponse, 'description': 'Новый email уже используется'},
        422: {'model': ErrorResponse, 'description': 'Некорректные данные профиля'},
    },
)
def update_current_profile(
    data: UserUpdate,
    current_user: CurrentUser,
    service: UserServiceDependency,
):
    return service.update_profile(current_user.id, data).to_dict()
