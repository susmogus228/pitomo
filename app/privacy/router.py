"""Consent choices are appended atomically with registration or profile updates."""
from datetime import datetime, timedelta, timezone
import hashlib
import json

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import func, select

from app.auth.dependencies import CurrentUser
from app.db.dependencies import SessionDependency
from app.db.models import ConsentReceiptORM, UserORM
from .documents import document_config, require_current_document
from .schemas import ConsentInput

router = APIRouter(tags=['Персональные данные'])


def latest_receipts(session, user_id):
    latest_ids = select(func.max(ConsentReceiptORM.id)).where(
        ConsentReceiptORM.user_id == user_id).group_by(ConsentReceiptORM.purpose)
    rows = session.scalars(select(ConsentReceiptORM).where(ConsentReceiptORM.id.in_(latest_ids))).all()
    latest = {}
    for row in rows:
        latest.setdefault(row.purpose, row)
    return latest


def record_consent(session, user_id, data: ConsentInput, config: dict, source: str):
    session.scalar(select(UserORM.id).where(UserORM.id == user_id).with_for_update())
    latest = latest_receipts(session, user_id)
    pending = []
    for purpose, accepted in [('service', True), ('analytics', data.analytics)]:
        previous = latest.get(purpose)
        decision = 'accepted' if accepted else 'withdrawn' if previous and previous.decision in {'accepted', 'withdrawn'} else 'declined'
        if previous and previous.decision == decision and previous.version == config['version'] and previous.subject_name == data.subject_name:
            continue
        pending.append((purpose, decision))
    recent = session.scalar(select(func.count(ConsentReceiptORM.id)).where(
        ConsentReceiptORM.user_id == user_id,
        ConsentReceiptORM.created_at >= datetime.now(timezone.utc) - timedelta(hours=1))) or 0
    if pending and recent + len(pending) > 30:
        raise HTTPException(429, 'Слишком много изменений согласий. Попробуйте позже; отзыв аналитики по-прежнему доступен')
    for purpose, decision in pending:
        snapshot = json.dumps({'version': config['version'], 'draft': config['draft'],
                               'operator': config['operator'], 'sections': config['sections'],
                               'purpose': config[purpose]}, ensure_ascii=False, sort_keys=True)
        session.add(ConsentReceiptORM(user_id=user_id, purpose=purpose, decision=decision,
                    version=config['version'], subject_name=data.subject_name, document=snapshot,
                    document_sha256=hashlib.sha256(snapshot.encode()).hexdigest(), source=source,
                    created_at=datetime.now(timezone.utc)))
    session.flush()


def consent_status(session, user_id):
    config = document_config(session.info['settings'])
    latest = latest_receipts(session, user_id)
    def item(row):
        return {'decision': row.decision, 'version': row.version, 'subject_name': row.subject_name,
                'created_at': row.created_at, 'source': row.source, 'document_sha256': row.document_sha256}
    return {'version': config['version'], 'service': item(latest['service']) if 'service' in latest else None,
            'analytics': item(latest['analytics']) if 'analytics' in latest else None,
            'analytics_collection_active': False,
            'analytics_allowed': bool(latest.get('analytics') and latest['analytics'].decision == 'accepted'
                                      and latest['analytics'].version == config['version'])}


@router.get('/api/v1/privacy/config')
def privacy_config(request: Request):
    return document_config(request.app.state.settings)


@router.get('/api/v1/users/me/consents')
def get_consents(current_user: CurrentUser, session: SessionDependency):
    return consent_status(session, current_user.id)


@router.post('/api/v1/users/me/consents')
def update_consents(data: ConsentInput, current_user: CurrentUser, session: SessionDependency):
    config = require_current_document(session.info['settings'], data.version)
    record_consent(session, current_user.id, data, config, 'profile')
    return consent_status(session, current_user.id)


@router.delete('/api/v1/users/me/consents/analytics', status_code=204)
def withdraw_analytics(current_user: CurrentUser, session: SessionDependency):
    # Withdrawal does not require accepting a changed document first.
    session.scalar(select(UserORM.id).where(UserORM.id == current_user.id).with_for_update())
    previous = latest_receipts(session, current_user.id).get('analytics')
    if previous and previous.decision == 'accepted':
        session.add(ConsentReceiptORM(user_id=current_user.id, purpose='analytics', decision='withdrawn',
                    version=previous.version, subject_name=previous.subject_name, document=previous.document,
                    document_sha256=previous.document_sha256, source='profile', created_at=datetime.now(timezone.utc)))
    return Response(status_code=204)
