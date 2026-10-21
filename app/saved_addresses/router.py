"""Owner-only address CRUD, serialized on the same stable user lock as carts."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select

from app.auth.dependencies import CurrentUser
from app.cart.repository import SQLAlchemyCartRepository
from app.db.dependencies import SessionDependency
from app.db.models import SavedAddressORM

router = APIRouter(prefix='/api/v1/users/me/addresses', tags=['Сохранённые адреса'])
AddressId = Annotated[int, Path(gt=0, le=2147483647)]
Source = Literal['manual', 'geoapify', 'map', 'geolocation']


class AddressFields(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    label: str = Field(default='Адрес', min_length=1, max_length=80)
    city: str = Field(min_length=1, max_length=120)
    street: str = Field(min_length=1, max_length=200)
    house: str = Field(min_length=1, max_length=40)
    details: str = Field(default='', max_length=200)
    lat: Decimal | None = Field(default=None, ge=-90, le=90, max_digits=10, decimal_places=7)
    lon: Decimal | None = Field(default=None, ge=-180, le=180, max_digits=10, decimal_places=7)
    source: Source = 'manual'
    is_default: bool = Field(default=False, strict=True)

    @model_validator(mode='after')
    def point_pair(self):
        if (self.lat is None) != (self.lon is None):
            raise ValueError('Координаты указываются парой')
        return self


class AddressCreate(AddressFields):
    expected_user_id: int | None = Field(default=None, strict=True, gt=0, le=2147483647)


class AddressPatch(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    label: str | None = Field(default=None, min_length=1, max_length=80)
    city: str | None = Field(default=None, min_length=1, max_length=120)
    street: str | None = Field(default=None, min_length=1, max_length=200)
    house: str | None = Field(default=None, min_length=1, max_length=40)
    details: str | None = Field(default=None, max_length=200)
    lat: Decimal | None = Field(default=None, ge=-90, le=90, max_digits=10, decimal_places=7)
    lon: Decimal | None = Field(default=None, ge=-180, le=180, max_digits=10, decimal_places=7)
    source: Source | None = None
    is_default: bool | None = Field(default=None, strict=True)
    expected_user_id: int | None = Field(default=None, strict=True, gt=0, le=2147483647)


class AddressResponse(AddressFields):
    model_config = ConfigDict(from_attributes=True)
    id: int
    lat: float | None = None
    lon: float | None = None
    created_at: datetime
    updated_at: datetime


class AddressList(BaseModel):
    items: list[AddressResponse]
    limit: int = 20


def _rows(session, user_id):
    return list(session.scalars(select(SavedAddressORM).where(
        SavedAddressORM.user_id == user_id).order_by(SavedAddressORM.id)))


def _guard_owner(user_id, expected_user_id):
    if expected_user_id is not None and expected_user_id != user_id:
        raise HTTPException(409, 'Аккаунт изменился. Обновите страницу.')


def _owned(rows, address_id):
    row = next((row for row in rows if row.id == address_id), None)
    if row is None:
        raise HTTPException(404, 'Адрес не найден')
    return row


def _make_default(session, rows, chosen):
    # Flush the old flag before the new one to satisfy the partial unique index.
    for row in rows:
        if row.id != chosen.id and row.is_default:
            row.is_default = False
    session.flush()
    chosen.is_default = True


@router.get('', response_model=AddressList)
def addresses(user: CurrentUser, session: SessionDependency):
    return {'items': _rows(session, user.id), 'limit': 20}


@router.post('', response_model=AddressResponse, status_code=201)
def create_address(data: AddressCreate, user: CurrentUser, session: SessionDependency):
    _guard_owner(user.id, data.expected_user_id)
    SQLAlchemyCartRepository(session).lock_user(user.id)
    rows = _rows(session, user.id)
    if len(rows) >= 20:
        raise HTTPException(409, 'Можно сохранить не больше 20 адресов')
    now = datetime.now(timezone.utc)
    values = data.model_dump(exclude={'expected_user_id'})
    wanted_default = values.pop('is_default') or not rows
    row = SavedAddressORM(user_id=user.id, **values, is_default=False, created_at=now, updated_at=now)
    session.add(row)
    session.flush()
    if wanted_default:
        _make_default(session, rows, row)
    session.flush()
    return row


@router.patch('/{address_id}', response_model=AddressResponse)
def update_address(address_id: AddressId, data: AddressPatch, user: CurrentUser, session: SessionDependency):
    _guard_owner(user.id, data.expected_user_id)
    SQLAlchemyCartRepository(session).lock_user(user.id)
    rows = _rows(session, user.id)
    row = _owned(rows, address_id)
    values = {key: getattr(row, key) for key in AddressFields.model_fields}
    values.update(data.model_dump(exclude_unset=True, exclude={'expected_user_id'}))
    try:
        checked = AddressFields.model_validate(values)
    except ValidationError as exc:
        raise HTTPException(422, 'Проверьте адрес и пару координат') from exc
    if row.is_default and not checked.is_default:
        raise HTTPException(409, 'Сначала выберите другой основной адрес')
    if checked.is_default:
        _make_default(session, rows, row)
    for key, value in checked.model_dump().items():
        setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)
    session.flush()
    return row


@router.delete('/{address_id}', status_code=204)
def delete_address(address_id: AddressId, user: CurrentUser, session: SessionDependency):
    SQLAlchemyCartRepository(session).lock_user(user.id)
    rows = _rows(session, user.id)
    row = _owned(rows, address_id)
    was_default = row.is_default
    session.delete(row)
    session.flush()
    remaining = [item for item in rows if item.id != address_id]
    if was_default and remaining:
        remaining[0].is_default = True
        remaining[0].updated_at = datetime.now(timezone.utc)
        session.flush()
    return Response(status_code=204)
