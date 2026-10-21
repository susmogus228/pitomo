"""User profile use cases."""
from __future__ import annotations

from .exceptions import EmailAlreadyExistsError, InvalidUserDataError, UserNotFoundError
from .models import User
from .repository import UserRepository
from .schemas import UserUpdate


class UserService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    def get_user(self, user_id: int) -> User:
        user = self.repository.get(user_id)
        if user is None:
            raise UserNotFoundError('Пользователь не найден')
        return user

    def update_profile(self, user_id: int, data: UserUpdate) -> User:
        user = self.get_user(user_id)
        changes = data.model_dump(exclude_unset=True)

        if 'email' in changes:
            if changes['email'] is None:
                raise InvalidUserDataError('Email не может быть null')
            existing = self.repository.get_by_email(changes['email'])
            if existing is not None and existing.id != user.id:
                raise EmailAlreadyExistsError('Пользователь с таким email уже существует')

        if 'first_name' in changes and changes['first_name'] is None:
            raise InvalidUserDataError('Имя не может быть null')

        try:
            if 'email' in changes:
                user.change_email(changes['email'])
            if 'first_name' in changes:
                user.change_first_name(changes['first_name'])
            if 'last_name' in changes:
                if changes['last_name'] is None:
                    user.change_last_name(None)
                else:
                    user.change_last_name(changes['last_name'])
        except ValueError as exc:
            raise InvalidUserDataError(str(exc)) from exc

        return self.repository.save(user, fields=set(changes))
