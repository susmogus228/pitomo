"""Serialize review threads without exposing email or private order details."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import OrderItemORM, OrderORM, ReviewORM, ReviewPhotoORM, ReviewReplyORM, UserORM
from .schemas import PhotoResponse, ReplyResponse, ReviewResponse


def photo_payloads(session: Session, *, review_id: int | None = None,
                   reply_id: int | None = None) -> list[PhotoResponse]:
    criterion = ReviewPhotoORM.review_id == review_id if review_id is not None else ReviewPhotoORM.reply_id == reply_id
    rows = session.scalars(select(ReviewPhotoORM).where(
        criterion, ReviewPhotoORM.deleted_at.is_(None)).order_by(ReviewPhotoORM.id)).all()
    return [PhotoResponse(id=row.id, url=f'/media/reviews/{row.filename}') for row in rows]


def reply_payload(session: Session, row: ReviewReplyORM, name: str | None = None) -> ReplyResponse:
    if name is None:
        author = session.get(UserORM, row.user_id)
        name = author.first_name if author else None
    return ReplyResponse(id=row.id, parent_reply_id=row.parent_reply_id,
                         author_id=row.user_id, author_name=name or 'Покупатель',
                         body='' if row.deleted_at else row.body,
                         created_at=row.created_at, updated_at=row.updated_at,
                         edited_at=row.edited_at, is_edited=row.edited_at is not None,
                         is_official=row.is_official, is_pinned=row.is_pinned,
                         is_deleted=row.deleted_at is not None,
                         photos=[] if row.deleted_at else photo_payloads(session, reply_id=row.id))


def review_payload(session: Session, row: ReviewORM, name: str | None = None) -> ReviewResponse:
    if name is None:
        author = session.get(UserORM, row.user_id)
        name = author.first_name if author else None
    replies = session.scalars(select(ReviewReplyORM).where(ReviewReplyORM.review_id == row.id)).all()
    names = dict(session.execute(select(UserORM.id, UserORM.first_name)
                .where(UserORM.id.in_({reply.user_id for reply in replies}))).all()) if replies else {}
    replies.sort(key=lambda reply: (not reply.is_pinned, reply.created_at, reply.id))
    verified = session.scalar(select(OrderORM.id).where(
        OrderORM.id == row.order_id, OrderORM.user_id == row.user_id,
        OrderORM.status == 'created', OrderORM.received_at.is_not(None),
        select(OrderItemORM.id).where(OrderItemORM.order_id == OrderORM.id,
                                      OrderItemORM.product_id == row.product_id).exists()).limit(1)) is not None
    return ReviewResponse(id=row.id, rating=row.rating,
                          body='' if row.deleted_at else row.body,
                          created_at=row.created_at, updated_at=row.updated_at,
                          edited_at=row.edited_at, is_edited=row.edited_at is not None,
                          verified_purchase=verified, is_hidden=row.hidden_at is not None,
                          author_id=row.user_id, author_name=name or 'Покупатель',
                          is_deleted=row.deleted_at is not None,
                          photos=[] if row.deleted_at else photo_payloads(session, review_id=row.id),
                          replies=[reply_payload(session, reply, names.get(reply.user_id)) for reply in replies])
