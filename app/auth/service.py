"""Registration, login and token authentication use cases."""
from __future__ import annotations

from app.core.config import Settings
from app.core.security import TokenError, create_access_token, decode_access_token, hash_password, password_needs_rehash, verify_password
from app.users.exceptions import EmailAlreadyExistsError, InvalidUserDataError
from app.users.models import User
from app.users.repository import UserRepository

from .exceptions import InvalidCredentialsError, InvalidTokenError
from .schemas import UserLogin, UserRegister


class AuthService:
    def __init__(self, repository: UserRepository, settings: Settings):
        self.repository = repository
        self.settings = settings

    def register(self, data: UserRegister) -> User:
        if self.repository.get_by_email(data.email) is not None:
            raise EmailAlreadyExistsError('Пользователь с таким email уже существует')

        try:
            user = User(
                id=self.repository.next_user_id(),
                email=data.email,
                password_hash=hash_password(data.password),
                first_name=data.first_name,
                last_name=data.last_name,
            )
        except ValueError as exc:
            raise InvalidUserDataError(str(exc)) from exc
        return self.repository.add(user)

    def login(self, data: UserLogin) -> dict[str, str | int]:
        user = self.repository.get_by_email(data.email)
        if user is None or not user.is_active or not verify_password(data.password, user.password_hash):
            raise InvalidCredentialsError('Неверный email или пароль')

        if password_needs_rehash(user.password_hash):
            if not self.repository.rehash_password(user.id, user.password_hash, hash_password(data.password)):
                raise InvalidCredentialsError('Неверный email или пароль')

        token = create_access_token(
            subject=user.id,
            secret=self.settings.jwt_secret,
            expires_minutes=self.settings.access_token_minutes,
        )
        return {
            'access_token': token,
            'token_type': 'bearer',
            'expires_in': self.settings.access_token_minutes * 60,
        }

    def user_from_token(self, token: str) -> User:
        try:
            payload = decode_access_token(token, secret=self.settings.jwt_secret)
            user_id = int(payload['sub'])
        except (TokenError, KeyError, TypeError, ValueError) as exc:
            raise InvalidTokenError('Недействительный или просроченный токен') from exc

        user = self.repository.get(user_id)
        if user is None or not user.is_active:
            raise InvalidTokenError('Недействительный или просроченный токен')
        return user
