"""Owner-controlled edits, bounded discussion and image attachments."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path as ApiPath, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.db.dependencies import get_db_session
from app.db.models import ReviewORM, ReviewReplyORM, ReviewPhotoORM
from .schemas import ReviewUpdate, ReplyCreate, ReplyUpdate, ReviewResponse, ReplyResponse
from .serialization import review_payload, reply_payload

router = APIRouter(prefix='/api/v1/products/{product_id}/reviews', tags=['Отзывы'])
DbSession = Annotated[Session, Depends(get_db_session, scope='function')]
PositiveId = Annotated[int, ApiPath(gt=0, le=2147483647)]


def get_review(session: Session, product_id: int, review_id: int) -> ReviewORM:
    row = session.scalar(select(ReviewORM).where(ReviewORM.id == review_id).with_for_update())
    if row is None or row.product_id != product_id or row.deleted_at is not None or row.hidden_at is not None:
        raise HTTPException(404, 'Отзыв не найден')
    return row


def get_reply(session: Session, review_id: int, reply_id: int) -> ReviewReplyORM:
    row = session.get(ReviewReplyORM, reply_id)
    if row is None or row.review_id != review_id or row.deleted_at is not None:
        raise HTTPException(404, 'Ответ не найден')
    return row


def require_owner(user_id: int, owner_id: int) -> None:
    if user_id != owner_id:
        raise HTTPException(403, 'Изменять запись может только автор')


def _erase_photos(session: Session, *, review_id: int | None = None,
                  reply_id: int | None = None) -> None:
    criterion = ReviewPhotoORM.review_id == review_id if review_id is not None else ReviewPhotoORM.reply_id == reply_id
    for photo in session.scalars(select(ReviewPhotoORM).where(
            criterion, ReviewPhotoORM.deleted_at.is_(None))).all():
        session.info.setdefault('deleted_uploads', []).append(
            Path(session.info['settings'].review_upload_dir) / photo.filename)
        photo.deleted_at = datetime.now(timezone.utc)


@router.patch('/{review_id}', response_model=ReviewResponse)
def update_review(product_id: PositiveId, review_id: PositiveId, data: ReviewUpdate,
                  current_user: CurrentUser, session: DbSession):
    review = get_review(session, product_id, review_id)
    require_owner(current_user.id, review.user_id)
    if not data.model_fields_set or ('rating' in data.model_fields_set and data.rating is None) or (
            'body' in data.model_fields_set and data.body is None):
        raise HTTPException(422, 'Укажите допустимые изменения')
    changed = ('rating' in data.model_fields_set and review.rating != data.rating) or (
        'body' in data.model_fields_set and review.body != data.body)
    if 'rating' in data.model_fields_set:
        review.rating = data.rating
    if 'body' in data.model_fields_set:
        review.body = data.body
    if changed:
        review.updated_at = datetime.now(timezone.utc)
        review.edited_at = review.updated_at
    return review_payload(session, review, current_user.first_name)


@router.delete('/{review_id}', status_code=204)
def delete_review(product_id: PositiveId, review_id: PositiveId,
                  current_user: CurrentUser, session: DbSession):
    review = get_review(session, product_id, review_id)
    require_owner(current_user.id, review.user_id)
    review.deleted_at = datetime.now(timezone.utc)
    review.body = ''
    review.updated_at = review.deleted_at
    _erase_photos(session, review_id=review.id)
    for reply in session.scalars(select(ReviewReplyORM).where(ReviewReplyORM.review_id == review.id)).all():
        _erase_photos(session, reply_id=reply.id)
        reply.deleted_at = review.deleted_at
        reply.body = ''
    return Response(status_code=204)


@router.post('/{review_id}/replies', response_model=ReplyResponse, status_code=201)
def create_reply(product_id: PositiveId, review_id: PositiveId, data: ReplyCreate,
                 current_user: CurrentUser, session: DbSession):
    get_review(session, product_id, review_id)
    if data.official and not current_user.is_admin:
        raise HTTPException(403, 'Официальный ответ доступен только администратору')
    recent = session.scalar(select(func.count(ReviewReplyORM.id)).where(
        ReviewReplyORM.user_id == current_user.id,
        ReviewReplyORM.created_at >= datetime.now(timezone.utc) - timedelta(hours=1))) or 0
    if recent >= 20:
        raise HTTPException(429, 'Лимит ответов: 20 в час')
    if data.parent_reply_id is not None:
        parent = get_reply(session, review_id, data.parent_reply_id)
        if parent.parent_reply_id is not None:
            raise HTTPException(422, 'Допускается один уровень ответов')
    if data.official and data.parent_reply_id is None:
        existing = session.scalar(select(ReviewReplyORM.id).where(ReviewReplyORM.review_id == review_id,
            ReviewReplyORM.is_pinned.is_(True), ReviewReplyORM.deleted_at.is_(None)).limit(1))
        if existing is not None:
            raise HTTPException(409, 'Официальный ответ уже опубликован')
    now = datetime.now(timezone.utc)
    reply = ReviewReplyORM(review_id=review_id, parent_reply_id=data.parent_reply_id,
                           user_id=current_user.id, body=data.body, is_official=data.official,
                           is_pinned=data.official and data.parent_reply_id is None,
                           created_at=now, updated_at=now)
    session.add(reply)
    session.flush()
    return reply_payload(session, reply, current_user.first_name)


@router.patch('/{review_id}/replies/{reply_id}', response_model=ReplyResponse)
def update_reply(product_id: PositiveId, review_id: PositiveId, reply_id: PositiveId,
                 data: ReplyUpdate, current_user: CurrentUser, session: DbSession):
    get_review(session, product_id, review_id)
    reply = get_reply(session, review_id, reply_id)
    require_owner(current_user.id, reply.user_id)
    if reply.body != data.body:
        reply.body = data.body
        reply.updated_at = datetime.now(timezone.utc)
        reply.edited_at = reply.updated_at
    return reply_payload(session, reply, current_user.first_name)


@router.delete('/{review_id}/replies/{reply_id}', status_code=204)
def delete_reply(product_id: PositiveId, review_id: PositiveId, reply_id: PositiveId,
                 current_user: CurrentUser, session: DbSession):
    get_review(session, product_id, review_id)
    reply = get_reply(session, review_id, reply_id)
    require_owner(current_user.id, reply.user_id)
    reply.deleted_at = datetime.now(timezone.utc)
    reply.body = ''
    reply.updated_at = reply.deleted_at
    _erase_photos(session, reply_id=reply.id)
    return Response(status_code=204)
