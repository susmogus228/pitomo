"""Authentication throttling across independent runtime instances."""
from concurrent.futures import ThreadPoolExecutor
import os

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.main import create_test_app
from tests.test_postgresql import pg_empty  # noqa: F401

pytestmark = pytest.mark.postgresql


def test_login_limit_is_atomic_across_application_instances(pg_empty):  # noqa: F811 - imported pytest fixture
    pg_empty.create_schema()
    with pg_empty.engine.connect() as connection:
        schema = connection.scalar(text('SELECT current_schema()'))
    url = make_url(os.environ['PETSHOP_TEST_POSTGRES_URL']).update_query_dict(
        {'options': f'-csearch_path={schema}'}
    ).render_as_string(hide_password=False)
    settings = Settings.for_testing(login_max_attempts=5)
    clients = [TestClient(create_test_app(url, settings=settings)) for _ in range(2)]
    credentials = {'email': 'shared-limit@example.com', 'password': 'not-the-password'}

    def attempt(index):
        return clients[index % 2].post('/api/v1/auth/login', json=credentials).status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(attempt, range(12)))
    assert statuses.count(401) == 5
    assert statuses.count(429) == 7
    with pg_empty.engine.connect() as connection:
        keys = connection.execute(text('SELECT key FROM login_attempts')).scalars().all()
    assert len(keys) == 2
    assert all(credentials['email'] not in key for key in keys)
