"""Bounded photo upload; public files contain re-encoded pixels only."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
import os
from pathlib import Path
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Path as ApiPath, Response, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.db.dependencies import get_db_session
from app.db.models import ReviewPhotoORM, ReviewORM, ReviewReplyORM, UserORM
from .extended import get_reply, get_review, require_owner
from .schemas import PhotoResponse

router = APIRouter(prefix='/api/v1/products/{product_id}/reviews', tags=['Отзывы'])
DbSession = Annotated[Session, Depends(get_db_session, scope='function')]
PositiveId = Annotated[int, ApiPath(gt=0, le=2147483647)]
MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 12_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def _webp(file: UploadFile, *, preserve_alpha: bool = False) -> bytes:
    if file.content_type not in {'image/jpeg', 'image/png', 'image/webp'}:
        raise HTTPException(422, 'Допустимы только JPEG, PNG и WebP')
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, 'Фото должно быть не больше 5 МиБ')
    try:
        with Image.open(BytesIO(data)) as source:
            if source.format not in {'JPEG', 'PNG', 'WEBP'} or source.width * source.height > MAX_PIXELS:
                raise HTTPException(422, 'Недопустимый формат или размер изображения')
            source.verify()
        with Image.open(BytesIO(data)) as source:
            pixels = ImageOps.exif_transpose(source)
            transparent = 'A' in pixels.getbands() or 'transparency' in pixels.info
            pixels = pixels.convert('RGBA' if preserve_alpha and transparent else 'RGB')
            if pixels.width > 2400 or pixels.height > 2400:
                pixels.thumbnail((2400, 2400))
            output = BytesIO()
            pixels.save(output, format='WEBP', quality=82, method=4)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, 'Файл не является допустимым изображением') from exc


def _upload(session: Session, upload: UploadFile, *, review_id: int | None = None,
            reply_id: int | None = None, uploader_id: int) -> PhotoResponse:
    # Serialize one uploader's inserts and additions to the same parent in
    # PostgreSQL, so hourly and per-parent limits survive parallel requests.
    session.scalar(select(UserORM.id).where(UserORM.id == uploader_id).with_for_update())
    # Serialize concurrent additions to the same parent in PostgreSQL, so the
    # three-photo limit cannot be bypassed with parallel requests.
    if review_id is not None:
        session.scalar(select(ReviewORM.id).where(ReviewORM.id == review_id).with_for_update())
    else:
        session.scalar(select(ReviewReplyORM.id).where(ReviewReplyORM.id == reply_id).with_for_update())
    criterion = ReviewPhotoORM.review_id == review_id if review_id is not None else ReviewPhotoORM.reply_id == reply_id
    count = session.scalar(select(func.count(ReviewPhotoORM.id)).where(
        criterion, ReviewPhotoORM.deleted_at.is_(None))) or 0
    if count >= 3:
        raise HTTPException(409, 'Можно прикрепить не более трёх фото')
    recent = session.scalar(select(func.count(ReviewPhotoORM.id)).where(
        ReviewPhotoORM.uploader_id == uploader_id,
        ReviewPhotoORM.created_at >= datetime.now(timezone.utc) - timedelta(hours=1))) or 0
    if recent >= 12:
        raise HTTPException(429, 'Лимит загрузки: 12 фото в час')
    encoded = _webp(upload)
    folder = Path(session.info['settings'].review_upload_dir)
    folder.mkdir(parents=True, exist_ok=True, mode=0o755)
    name = uuid.uuid4().hex + '.webp'
    target = folder / name
    temporary = folder / (name + '.tmp')
    # Only completed re-encoded files receive a public .webp name.
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        if hasattr(os, 'fchmod'):
            os.fchmod(fd, 0o644)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(encoded)
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    session.info.setdefault('created_uploads', []).append(target)
    row = ReviewPhotoORM(review_id=review_id, reply_id=reply_id,
                         uploader_id=uploader_id,
                         filename=name, created_at=datetime.now(timezone.utc))
    session.add(row)
    session.flush()
    return PhotoResponse(id=row.id, url=f'/media/reviews/{name}')


def _delete(session: Session, row: ReviewPhotoORM) -> None:
    target = Path(session.info['settings'].review_upload_dir) / row.filename
    row.deleted_at = datetime.now(timezone.utc)
    session.info.setdefault('deleted_uploads', []).append(target)


@router.post('/{review_id}/photos', response_model=PhotoResponse, status_code=201)
def upload_review_photo(product_id: PositiveId, review_id: PositiveId,
                        file: Annotated[UploadFile, File()],
                        current_user: CurrentUser, session: DbSession):
    review = get_review(session, product_id, review_id)
    require_owner(current_user.id, review.user_id)
    return _upload(session, file, review_id=review_id, uploader_id=current_user.id)


@router.delete('/{review_id}/photos/{photo_id}', status_code=204)
def delete_review_photo(product_id: PositiveId, review_id: PositiveId,
                        photo_id: PositiveId, current_user: CurrentUser, session: DbSession):
    review = get_review(session, product_id, review_id)
    require_owner(current_user.id, review.user_id)
    row = session.get(ReviewPhotoORM, photo_id)
    if row is None or row.review_id != review_id or row.deleted_at is not None:
        raise HTTPException(404, 'Фото не найдено')
    _delete(session, row)
    return Response(status_code=204)


@router.post('/{review_id}/replies/{reply_id}/photos', response_model=PhotoResponse, status_code=201)
def upload_reply_photo(product_id: PositiveId, review_id: PositiveId, reply_id: PositiveId,
                       file: Annotated[UploadFile, File()],
                       current_user: CurrentUser, session: DbSession):
    get_review(session, product_id, review_id)
    reply = get_reply(session, review_id, reply_id)
    require_owner(current_user.id, reply.user_id)
    return _upload(session, file, reply_id=reply_id, uploader_id=current_user.id)


@router.delete('/{review_id}/replies/{reply_id}/photos/{photo_id}', status_code=204)
def delete_reply_photo(product_id: PositiveId, review_id: PositiveId, reply_id: PositiveId,
                       photo_id: PositiveId, current_user: CurrentUser, session: DbSession):
    get_review(session, product_id, review_id)
    reply = get_reply(session, review_id, reply_id)
    require_owner(current_user.id, reply.user_id)
    row = session.get(ReviewPhotoORM, photo_id)
    if row is None or row.reply_id != reply_id or row.deleted_at is not None:
        raise HTTPException(404, 'Фото не найдено')
    _delete(session, row)
    return Response(status_code=204)
