"""Admin-only product photos, stored as bounded, re-encoded public pixels."""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Annotated
import uuid

from fastapi import APIRouter, File, Form, HTTPException, Path as ApiPath, UploadFile
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.dependencies import AdminUser
from app.db.dependencies import SessionDependency
from app.db.models import ProductORM, ProductPhotoORM
from app.reviews.media import _webp

from .router import ServiceDependency, _with_ratings
from .schemas import ProductCreate, ProductResponse

router = APIRouter(prefix='/api/v1/products', tags=['Фото товаров'])
PositiveId = Annotated[int, ApiPath(gt=0, le=2147483647)]
MAX_PHOTOS = 5


def _product(session: Session, product_id: int) -> ProductORM:
    # SQLite has no FOR UPDATE; acquire its writer lock before counting photos.
    if session.get_bind().dialect.name == 'sqlite':
        session.execute(update(ProductORM).where(ProductORM.id == product_id).values(id=ProductORM.id))
    row = session.scalar(select(ProductORM).where(ProductORM.id == product_id)
                         .with_for_update().execution_options(populate_existing=True))
    if row is None:
        raise HTTPException(404, 'Товар не найден')
    return row


def _photos(session: Session, product_id: int) -> list[ProductPhotoORM]:
    return list(session.scalars(select(ProductPhotoORM).where(
        ProductPhotoORM.product_id == product_id).order_by(
            ProductPhotoORM.created_at, ProductPhotoORM.id)))


def _photo(session: Session, product_id: int, photo_id: int) -> ProductPhotoORM:
    row = session.scalar(select(ProductPhotoORM).where(
        ProductPhotoORM.id == photo_id, ProductPhotoORM.product_id == product_id))
    if row is None:
        raise HTTPException(404, 'Фото не найдено')
    return row


def _url(photo: ProductPhotoORM) -> str:
    return f'/media/products/{photo.filename}'


def _save(session: Session, product: ProductORM, pixels: bytes) -> ProductPhotoORM:
    folder = Path(session.info['settings'].review_upload_dir) / 'products'
    name = uuid.uuid4().hex + '.webp'
    target, temporary = folder / name, folder / (name + '.tmp')
    try:
        folder.mkdir(parents=True, exist_ok=True, mode=0o755)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, 'wb') as stream:
            if hasattr(os, 'fchmod'):
                os.fchmod(stream.fileno(), 0o644)
            stream.write(pixels)
        os.replace(temporary, target)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(503, 'Не удалось сохранить фото. Повторите позже.') from exc
    session.info.setdefault('created_uploads', []).append(target)
    photo = ProductPhotoORM(product_id=product.id, filename=name,
                            created_at=datetime.now(timezone.utc))
    session.add(photo)
    session.flush()
    return photo


def _response(session: Session, service, product_id: int) -> dict:
    session.flush()
    return _with_ratings([service.get_product(product_id).to_dict()], session)[0]


@router.post('/with-photos', response_model=ProductResponse, status_code=201,
             summary='Создать товар вместе с фотографиями')
def create_with_photos(data: Annotated[str, Form(max_length=65536)],
                       admin: AdminUser, session: SessionDependency, service: ServiceDependency,
                       files: Annotated[list[UploadFile] | None, File()] = None):
    uploads = files or []
    if len(uploads) > MAX_PHOTOS:
        raise HTTPException(422, 'Можно прикрепить не более пяти фото')
    try:
        payload = ProductCreate.model_validate_json(data)
    except ValidationError as exc:
        issues = [{'type': error['type'], 'loc': list(error['loc']),
                   'msg': 'Invalid value' if error['type'] == 'value_error' else error['msg']}
                  for error in exc.errors(include_context=False, include_url=False)]
        raise HTTPException(422, issues) from exc
    # Validate every image before creating anything. The request transaction and
    # created_uploads rollback cleanup also cover write failures after creation.
    pixels = [_webp(file, preserve_alpha=True) for file in uploads]
    created = service.create_product(payload)
    product = _product(session, created.id)
    for encoded in pixels:
        photo = _save(session, product, encoded)
        if product.image_url is None:
            product.image_url = _url(photo)
    return _response(session, service, created.id)


@router.post('/{product_id}/photos', response_model=ProductResponse, status_code=201,
             summary='Добавить фотографию товара')
def upload_photo(product_id: PositiveId, file: Annotated[UploadFile, File()],
                 admin: AdminUser, session: SessionDependency, service: ServiceDependency):
    product = _product(session, product_id)
    photos = _photos(session, product_id)
    if len(photos) >= MAX_PHOTOS:
        raise HTTPException(409, 'Можно прикрепить не более пяти фото')
    photo = _save(session, product, _webp(file, preserve_alpha=True))
    if not photos:
        product.image_url = _url(photo)
    return _response(session, service, product_id)


@router.delete('/{product_id}/photos/{photo_id}', response_model=ProductResponse,
               summary='Удалить фотографию товара')
def delete_photo(product_id: PositiveId, photo_id: PositiveId,
                 admin: AdminUser, session: SessionDependency, service: ServiceDependency):
    product = _product(session, product_id)
    photo = _photo(session, product_id, photo_id)
    if product.image_url == _url(photo):
        remaining = [row for row in _photos(session, product_id) if row.id != photo_id]
        product.image_url = _url(remaining[0]) if remaining else None
    session.delete(photo)
    session.info.setdefault('deleted_uploads', []).append(
        Path(session.info['settings'].review_upload_dir) / 'products' / photo.filename)
    return _response(session, service, product_id)


@router.patch('/{product_id}/photos/{photo_id}/cover', response_model=ProductResponse,
              summary='Выбрать обложку товара')
def select_cover(product_id: PositiveId, photo_id: PositiveId,
                 admin: AdminUser, session: SessionDependency, service: ServiceDependency):
    product = _product(session, product_id)
    product.image_url = _url(_photo(session, product_id, photo_id))
    return _response(session, service, product_id)
