"""Domain entity for application users."""
from __future__ import annotations


VALID_USER_ROLES = frozenset({'customer', 'admin'})


class User:
    """Application user independent from FastAPI and storage implementation."""

    def __init__(
        self,
        id: int,
        email: str,
        password_hash: str,
        first_name: str,
        last_name: str | None = None,
        *,
        is_active: bool = True,
        role: str = 'customer',
    ):
        self.id = id
        self.change_email(email)
        self.password_hash = self._required_text(password_hash, 'Хэш пароля')
        self.rename(first_name, last_name)
        self.set_active(is_active)
        self.change_role(role)

    @staticmethod
    def _required_text(value: str, field_name: str) -> str:
        if value is None:
            raise ValueError(f'{field_name} не может быть пустым')
        value = str(value).strip()
        if not value:
            raise ValueError(f'{field_name} не может быть пустым')
        return value

    @staticmethod
    def _normalize_email(value: str) -> str:
        email = User._required_text(value, 'Email').casefold()
        if email.count('@') != 1:
            raise ValueError('Некорректный email')
        local, domain = email.split('@')
        if not local or '.' not in domain or domain.startswith('.') or domain.endswith('.'):
            raise ValueError('Некорректный email')
        return email

    def change_email(self, value: str) -> None:
        self.email = self._normalize_email(value)

    def rename(self, first_name: str, last_name: str | None = None) -> None:
        self.change_first_name(first_name)
        self.change_last_name(last_name)

    def change_first_name(self, value: str) -> None:
        self.first_name = self._required_text(value, 'Имя')

    def change_last_name(self, value: str | None) -> None:
        if value is None:
            self.last_name = None
        else:
            cleaned = str(value).strip()
            self.last_name = cleaned or None

    def change_password_hash(self, value: str) -> None:
        self.password_hash = self._required_text(value, 'Хэш пароля')

    def change_role(self, value: str) -> None:
        normalized = self._required_text(value, 'Роль').casefold()
        if normalized not in VALID_USER_ROLES:
            raise ValueError('Недопустимая роль пользователя')
        self.role = normalized

    def set_active(self, value: bool) -> None:
        self.is_active = bool(value)

    @property
    def is_admin(self) -> bool:
        return self.role == 'admin'

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'email': self.email,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'is_active': self.is_active,
            'role': self.role,
        }
