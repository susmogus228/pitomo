"""Administrative user-management use cases."""
from __future__ import annotations

from app.users.exceptions import InvalidUserDataError, UserNotFoundError
from app.users.models import User
from app.users.repository import UserRepository

from .exceptions import AdminSelfLockoutError
from .schemas import AdminUserUpdate


class AdminService:
    def __init__(self, users: UserRepository):
        self.users = users

    def list_users(self, *, limit: int = 50, offset: int = 0) -> tuple[User, ...]:
        return self.users.all(limit=limit, offset=offset)

    def get_user(self, user_id: int) -> User:
        user = self.users.get(user_id)
        if user is None:
            raise UserNotFoundError('Пользователь не найден')
        return user

    def update_user(self, actor: User, user_id: int, data: AdminUserUpdate) -> User:
        target = self.get_user(user_id)
        changes = data.model_dump(exclude_unset=True)

        if actor.id == target.id:
            if changes.get('role') == 'customer':
                raise AdminSelfLockoutError('Администратор не может снять собственную роль admin')
            if changes.get('is_active') is False:
                raise AdminSelfLockoutError('Администратор не может деактивировать самого себя')

        try:
            if 'role' in changes and changes['role'] is not None:
                target.change_role(changes['role'])
            if 'is_active' in changes and changes['is_active'] is not None:
                target.set_active(changes['is_active'])
        except ValueError as exc:
            raise InvalidUserDataError(str(exc)) from exc

        return self.users.save(target, fields=set(changes))
