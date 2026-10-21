"""Release connection pools even when legacy tests use non-context clients."""
import pytest

from app.db.session import Database


@pytest.fixture(autouse=True)
def dispose_test_databases(monkeypatch):
    databases = []
    original = Database.__init__

    def tracked_init(self, *args, **kwargs):
        original(self, *args, **kwargs)
        databases.append(self)

    monkeypatch.setattr(Database, '__init__', tracked_init)
    yield
    for database in reversed(databases):
        database.dispose()
