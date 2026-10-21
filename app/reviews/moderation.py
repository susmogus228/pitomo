"""Owner-private reports and administrator-only, journaled review moderation."""
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.auth.dependencies import AdminUser, CurrentUser
from app.db.dependencies import SessionDependency
from app.db.models import (ProductORM, ReviewModerationEventORM, ReviewORM,
                           ReviewReportORM, UserORM)
from .extended import get_review

router = APIRouter(prefix='/api/v1', tags=['Модерация отзывов'])
PositiveId = Annotated[int, Path(gt=0, le=2147483647)]


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    reason: Literal['spam', 'abuse', 'irrelevant', 'other']
    details: str = Field(default='', max_length=500)


class ModerationCommand(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    action: Literal['hide', 'restore', 'dismiss_reports']
    reason: str = Field(min_length=1, max_length=500)


@router.post('/products/{product_id}/reviews/{review_id}/reports', status_code=201)
def report_review(product_id: PositiveId, review_id: PositiveId, data: ReportCreate,
                  user: CurrentUser, session: SessionDependency, response: Response):
    session.scalar(select(UserORM.id).where(UserORM.id == user.id).with_for_update())
    review = get_review(session, product_id, review_id)
    if review.user_id == user.id:
        raise HTTPException(422, 'На собственный отзыв жаловаться нельзя')
    previous = session.scalar(select(ReviewReportORM).where(
        ReviewReportORM.review_id == review_id, ReviewReportORM.reporter_id == user.id))
    if previous is not None:
        response.status_code = 200
        return {'id': previous.id, 'status': previous.status, 'already_reported': True}
    recent = session.scalar(select(func.count(ReviewReportORM.id)).where(
        ReviewReportORM.reporter_id == user.id,
        ReviewReportORM.created_at >= datetime.now(timezone.utc) - timedelta(hours=1))) or 0
    if recent >= 10:
        raise HTTPException(429, 'Можно отправить не более десяти жалоб в час')
    row = ReviewReportORM(review_id=review_id, reporter_id=user.id, reason=data.reason,
                          details=data.details, status='pending', created_at=datetime.now(timezone.utc))
    session.add(row)
    session.flush()
    return {'id': row.id, 'status': row.status, 'already_reported': False}


@router.get('/admin/review-reports')
def reports(admin: AdminUser, session: SessionDependency,
            status: Literal['pending', 'dismissed', 'actioned', 'all'] = 'pending',
            limit: Annotated[int, Query(ge=1, le=100)] = 20,
            offset: Annotated[int, Query(ge=0, le=2147483647)] = 0):
    filters = [] if status == 'all' else [ReviewReportORM.status == status]
    total = session.scalar(select(func.count(ReviewReportORM.id)).where(*filters)) or 0
    rows = session.execute(select(ReviewReportORM, ReviewORM, ProductORM.name, UserORM.first_name)
        .join(ReviewORM, ReviewORM.id == ReviewReportORM.review_id)
        .outerjoin(ProductORM, ProductORM.id == ReviewORM.product_id)
        .join(UserORM, UserORM.id == ReviewORM.user_id)
        .where(*filters).order_by(ReviewReportORM.created_at.desc(), ReviewReportORM.id.desc())
        .limit(limit).offset(offset)).all()
    return {'items': [{'id': report.id, 'review_id': review.id, 'product_id': review.product_id,
                       'product_name': product_name or 'Товар удалён', 'author_name': author,
                       'body': review.body, 'rating': review.rating, 'reason': report.reason,
                       'details': report.details, 'status': report.status, 'created_at': report.created_at,
                       'is_hidden': review.hidden_at is not None, 'is_deleted': review.deleted_at is not None}
                      for report, review, product_name, author in rows],
            'total': total, 'limit': limit, 'offset': offset}


@router.post('/admin/reviews/{review_id}/moderation')
def moderate(review_id: PositiveId, data: ModerationCommand,
             admin: AdminUser, session: SessionDependency):
    review = session.scalar(select(ReviewORM).where(ReviewORM.id == review_id).with_for_update())
    if review is None:
        raise HTTPException(404, 'Отзыв не найден')
    if review.deleted_at is not None and data.action != 'dismiss_reports':
        raise HTTPException(409, 'Автор удалил отзыв; восстановление недоступно')
    now = datetime.now(timezone.utc)
    pending = session.scalars(select(ReviewReportORM).where(
        ReviewReportORM.review_id == review_id, ReviewReportORM.status == 'pending')).all()
    if data.action == 'hide':
        if review.hidden_at is not None:
            return {'review_id': review_id, 'is_hidden': True, 'resolved_reports': 0, 'unchanged': True}
        review.hidden_at = now
    elif data.action == 'restore':
        if review.hidden_at is None:
            return {'review_id': review_id, 'is_hidden': False, 'resolved_reports': 0, 'unchanged': True}
        review.hidden_at = None
    elif not pending:
        return {'review_id': review_id, 'is_hidden': review.hidden_at is not None,
                'resolved_reports': 0, 'unchanged': True}
    if data.action in {'hide', 'dismiss_reports'}:
        for report in pending:
            report.status = 'actioned' if data.action == 'hide' else 'dismissed'
            report.resolved_at = now
            report.resolved_by = admin.id
    session.add(ReviewModerationEventORM(review_id=review_id, admin_id=admin.id,
                                        action=data.action, reason=data.reason, created_at=now))
    session.flush()
    return {'review_id': review_id, 'is_hidden': review.hidden_at is not None,
            'resolved_reports': len(pending) if data.action != 'restore' else 0, 'unchanged': False}


@router.get('/admin/reviews/{review_id}/moderation')
def moderation_history(review_id: PositiveId, admin: AdminUser, session: SessionDependency,
                       limit: Annotated[int, Query(ge=1, le=100)] = 20,
                       offset: Annotated[int, Query(ge=0, le=2147483647)] = 0):
    if session.get(ReviewORM, review_id) is None:
        raise HTTPException(404, 'Отзыв не найден')
    condition = ReviewModerationEventORM.review_id == review_id
    total = session.scalar(select(func.count(ReviewModerationEventORM.id)).where(condition)) or 0
    rows = session.scalars(select(ReviewModerationEventORM).where(condition)
        .order_by(ReviewModerationEventORM.created_at.desc(), ReviewModerationEventORM.id.desc())
        .limit(limit).offset(offset)).all()
    return {'items': [{'id': row.id, 'action': row.action, 'reason': row.reason,
                       'admin_id': row.admin_id, 'created_at': row.created_at} for row in rows],
            'total': total, 'limit': limit, 'offset': offset}
