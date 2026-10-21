from dataclasses import replace
import hashlib

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select

from app.core.config import Settings
from app.db.models import ConsentReceiptORM, UserORM
from app.main import create_test_app
from app.privacy.documents import document_config
from tests.helpers import consent_payload


def register(client, *, analytics=False, email='consent@example.com'):
    return client.post('/api/v1/auth/register', json={
        'email': email, 'first_name': 'Tester', 'password': 'StrongPass123',
        'consent': consent_payload(client, 'Test Person', analytics),
    })


def headers(client, email='consent@example.com'):
    token = client.post('/api/v1/auth/login', json={'email': email, 'password': 'StrongPass123'}).json()['access_token']
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def client():
    with TestClient(create_test_app()) as client:
        yield client


@pytest.mark.parametrize('choice', [None, False, 'true', 1])
def test_registration_requires_explicit_boolean_service_consent(client, choice):
    body = {'email': 'missing@example.com', 'password': 'StrongPass123', 'first_name': 'Tester'}
    if choice is not None:
        body['consent'] = {**consent_payload(client), 'service': choice}
    assert client.post('/api/v1/auth/register', json=body).status_code == 422
    with client.app.state.database.session_factory() as session:
        assert session.scalar(select(func.count(UserORM.id))) == 0
        assert session.scalar(select(func.count(ConsentReceiptORM.id))) == 0


def test_declining_analytics_does_not_block_registration_and_receipt_has_snapshot(client):
    assert register(client).status_code == 201
    state = client.get('/api/v1/users/me/consents', headers=headers(client)).json()
    assert state['service']['decision'] == 'accepted'
    assert state['analytics']['decision'] == 'declined'
    assert not state['analytics_allowed']
    with client.app.state.database.session_factory() as session:
        rows = session.scalars(select(ConsentReceiptORM)).all()
        assert len(rows) == 2
        for row in rows:
            assert row.document_sha256 == hashlib.sha256(row.document.encode()).hexdigest()
            assert row.subject_name == 'Test Person'
            assert row.source == 'registration'
            assert 'Пароль' not in row.document
            assert '[БИН / ИИН' in row.document


def test_stale_version_is_rejected_without_creating_user(client):
    body = {'email': 'stale@example.com', 'password': 'StrongPass123', 'first_name': 'Tester',
            'consent': {**consent_payload(client), 'version': 'outdated'}}
    assert client.post('/api/v1/auth/register', json=body).status_code == 409
    with client.app.state.database.session_factory() as session:
        assert session.scalar(select(func.count(UserORM.id))) == 0


def test_choices_are_append_only_owned_and_withdrawal_is_idempotent(client):
    assert register(client, analytics=True).status_code == 201
    auth = headers(client)
    assert client.get('/api/v1/users/me/consents').status_code == 401
    assert client.get('/api/v1/users/me/consents', headers=auth).json()['analytics_allowed']
    assert client.delete('/api/v1/users/me/consents/analytics', headers=auth).status_code == 204
    assert client.delete('/api/v1/users/me/consents/analytics', headers=auth).status_code == 204
    state = client.get('/api/v1/users/me/consents', headers=auth).json()
    assert not state['analytics_allowed'] and state['analytics']['decision'] == 'withdrawn'
    with client.app.state.database.session_factory() as session:
        assert [r.decision for r in session.scalars(select(ConsentReceiptORM).where(
            ConsentReceiptORM.purpose == 'analytics').order_by(ConsentReceiptORM.id))] == ['accepted', 'withdrawn']
    assert register(client, email='another@example.com').status_code == 201
    other = client.get('/api/v1/users/me/consents', headers=headers(client, 'another@example.com')).json()
    assert other['analytics']['decision'] == 'declined'


def test_legacy_account_has_no_fabricated_consent_and_can_accept(client):
    from app.users.models import User
    from app.users.repository import SQLAlchemyUserRepository
    from app.core.security import hash_password
    with client.app.state.database.session_factory() as session:
        repo = SQLAlchemyUserRepository(session)
        repo.add(User(id=repo.next_user_id(), email='consent@example.com', password_hash=hash_password('StrongPass123'), first_name='Legacy'))
        session.commit()
    auth = headers(client)
    state = client.get('/api/v1/users/me/consents', headers=auth).json()
    assert state['service'] is None and state['analytics'] is None
    result = client.post('/api/v1/users/me/consents', headers=auth, json=consent_payload(client))
    assert result.status_code == 200
    assert result.json()['service']['source'] == 'profile'


def test_updated_document_disables_analytics_but_allows_withdrawal(client):
    assert register(client, analytics=True).status_code == 201
    auth = headers(client)
    client.app.state.settings = replace(client.app.state.settings, privacy_operator_name='Changed Owner')
    assert not client.get('/api/v1/users/me/consents', headers=auth).json()['analytics_allowed']
    assert client.delete('/api/v1/users/me/consents/analytics', headers=auth).status_code == 204


def test_production_blocks_placeholder_documents():
    settings = Settings.for_testing(environment='production', demo_payments=False)
    config = document_config(settings)
    assert config['draft'] and not config['registration_allowed']
    with TestClient(create_test_app(settings=settings)) as client:
        assert register(client).status_code == 503


def test_document_version_changes_with_operator_details():
    base = Settings.for_testing()
    complete = replace(base, privacy_operator_name='Example Operator', privacy_operator_id='123456789012',
                       privacy_contact_email='privacy@example.com', privacy_storage_country='KZ', privacy_documents_approved=True)
    assert document_config(base)['version'] != document_config(complete)['version']
    assert not document_config(complete)['draft']


def test_profile_declined_choice_is_idempotent_after_withdrawal(client):
    assert register(client, analytics=True).status_code == 201
    auth = headers(client)
    assert client.delete('/api/v1/users/me/consents/analytics', headers=auth).status_code == 204
    choice = consent_payload(client, 'Test Person', False)
    for _ in range(2):
        assert client.post('/api/v1/users/me/consents', headers=auth, json=choice).status_code == 200
    with client.app.state.database.session_factory() as session:
        assert session.scalar(select(func.count(ConsentReceiptORM.id))) == 3


def test_choice_write_limit_does_not_prevent_withdrawal(client):
    assert register(client, analytics=True).status_code == 201
    auth = headers(client)
    with client.app.state.database.session_factory() as session:
        original = session.scalar(select(ConsentReceiptORM).where(ConsentReceiptORM.purpose == 'service'))
        for _ in range(28):
            session.add(ConsentReceiptORM(user_id=original.user_id, purpose='service', decision='accepted',
                version=original.version, subject_name=original.subject_name, document=original.document,
                document_sha256=original.document_sha256, source='profile', created_at=original.created_at))
        session.commit()
    assert client.post('/api/v1/users/me/consents', headers=auth, json=consent_payload(client, 'Test Person', False)).status_code == 429
    assert client.delete('/api/v1/users/me/consents/analytics', headers=auth).status_code == 204
    assert not client.get('/api/v1/users/me/consents', headers=auth).json()['analytics_allowed']
