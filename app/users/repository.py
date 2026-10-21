"""Repository abstraction for user persistence."""
from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.mappers import user_to_domain
from app.db.models import UserORM
from app.db.identifiers import next_id
from app.db.errors import unique_violation
from .exceptions import EmailAlreadyExistsError, UserNotFoundError

from .models import User


class UserRepository(ABC):
    def rehash_password(self, user_id: int, expected_hash: str, replacement_hash: str) -> bool:
        user = self.get(user_id)
        if user is None or user.password_hash != expected_hash:
            return False
        user.password_hash = replacement_hash
        self.save(user, fields={'password_hash'})
        return True

    @abstractmethod
    def all(self, *, limit: int = 50, offset: int = 0) -> tuple[User, ...]:
        raise NotImplementedError

    @abstractmethod
    def get(self, user_id: int) -> User | None:
        raise NotImplementedError

    @abstractmethod
    def get_by_email(self, email: str) -> User | None:
        raise NotImplementedError

    @abstractmethod
    def add(self, user: User) -> User:
        raise NotImplementedError

    @abstractmethod
    def save(self, user: User, *, fields: set[str] | None = None) -> User:
        raise NotImplementedError

    @abstractmethod
    def next_user_id(self) -> int:
        raise NotImplementedError


class InMemoryUserRepository(UserRepository):
    """Legacy in-memory adapter retained for domain-level examples."""

    def __init__(self, users: tuple[User, ...] | list[User] = ()):
        self.__users = {user.id: user for user in users}
        self.__next_user_id = max(self.__users, default=0) + 1

    def all(self, *, limit: int = 50, offset: int = 0) -> tuple[User, ...]:
        return tuple(sorted(self.__users.values(), key=lambda u: u.id))[offset:offset + min(limit, 100)]

    def get(self, user_id: int) -> User | None:
        return self.__users.get(user_id)

    def get_by_email(self, email: str) -> User | None:
        normalized = email.strip().casefold()
        return next((user for user in self.__users.values() if user.email == normalized), None)

    def add(self, user: User) -> User:
        self.__users[user.id] = user
        return user

    def save(self, user: User, *, fields: set[str] | None = None) -> User:
        self.__users[user.id] = user
        return user

    def next_user_id(self) -> int:
        value = self.__next_user_id
        self.__next_user_id += 1
        return value


class SQLAlchemyUserRepository(UserRepository):
    def __init__(self, session: Session):
        self.session = session

    def rehash_password(self, user_id: int, expected_hash: str, replacement_hash: str) -> bool:
        result = self.session.execute(update(UserORM).where(
            UserORM.id == user_id, UserORM.password_hash == expected_hash,
        ).values(password_hash=replacement_hash))
        return result.rowcount == 1

    def all(self, *, limit: int = 50, offset: int = 0) -> tuple[User, ...]:
        rows = self.session.scalars(select(UserORM).order_by(UserORM.id).limit(min(limit, 100)).offset(offset)).all()
        return tuple(user_to_domain(row) for row in rows)

    def get(self, user_id: int) -> User | None:
        row = self.session.get(UserORM, user_id)
        return user_to_domain(row) if row is not None else None

    def get_by_email(self, email: str) -> User | None:
        normalized = email.strip().casefold()
        row = self.session.scalar(select(UserORM).where(UserORM.email == normalized))
        return user_to_domain(row) if row is not None else None

    def add(self, user: User) -> User:
        return self.save(user)

    def save(self, user: User, *, fields: set[str] | None = None) -> User:
        allowed = {'email', 'password_hash', 'first_name', 'last_name', 'is_active', 'role'}
        if fields is not None and not fields <= allowed:
            raise ValueError('Unsupported user fields')
        values = {field: getattr(user, field) for field in (allowed if fields is None else fields)}
        try:
            if fields is None:
                row = self.session.get(UserORM, user.id)
                if row is None:
                    row = UserORM(id=user.id)
                    self.session.add(row)
                for field, value in values.items():
                    setattr(row, field, value)
            elif values:
                result = self.session.execute(update(UserORM).where(UserORM.id == user.id).values(**values))
                if result.rowcount != 1:
                    raise UserNotFoundError('Пользователь не найден')
            self.session.flush()
        except IntegrityError as exc:
            if unique_violation(exc, names={'ix_users_email', 'users_email_key'}, sqlite_columns={'users.email'}):
                raise EmailAlreadyExistsError('Пользователь с таким email уже существует') from exc
            raise
        row = self.session.scalar(select(UserORM).where(UserORM.id == user.id).execution_options(populate_existing=True))
        return user_to_domain(row)

    def next_user_id(self) -> int:
        return next_id(self.session, UserORM)
