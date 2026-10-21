from app.users.repository import SQLAlchemyUserRepository


def consent_payload(client, subject_name='Test User', analytics=False):
    version = client.get('/api/v1/privacy/config').json()['version']
    return {'version': version, 'subject_name': subject_name, 'service': True, 'analytics': analytics}


def with_consent(client, payload):
    return {**payload, 'consent': payload.get('consent', consent_payload(client))}


def promote_user_to_admin(client, email: str) -> None:
    with client.app.state.database.session_factory() as session:
        repo = SQLAlchemyUserRepository(session)
        user = repo.get_by_email(email)
        assert user is not None
        user.change_role('admin')
        user.set_active(True)
        repo.save(user, fields={'role', 'is_active'})
        session.commit()


def admin_headers(client, email: str = 'test-admin@example.com') -> dict[str, str]:
    payload = {
        'email': email,
        'password': 'StrongAdmin123',
        'first_name': 'Test',
        'last_name': 'Admin',
    }
    response = client.post('/api/v1/auth/register', json=with_consent(client, payload))
    if response.status_code == 201:
        promote_user_to_admin(client, email)
    else:
        assert response.status_code == 409
        promote_user_to_admin(client, email)
    login = client.post('/api/v1/auth/login', json={'email': email, 'password': payload['password']})
    assert login.status_code == 200, login.text
    return {'Authorization': f"Bearer {login.json()['access_token']}"}
