from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.db.session import Database


def test_upgrade_preserves_existing_records_and_does_not_fabricate_consent(tmp_path):
    database = Database(f'sqlite+pysqlite:///{tmp_path / "migration.db"}')
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    config.attributes['database_url'] = database.url
    try:
        command.upgrade(config, '0009_v010')
        with database.engine.begin() as connection:
            connection.execute(text("INSERT INTO users(id,email,password_hash,first_name,is_active,role) VALUES(1,'synthetic@example.test','hash','Legacy',1,'customer')"))
        command.upgrade(config, 'head')
        with database.engine.connect() as connection:
            assert connection.scalar(text('SELECT COUNT(*) FROM users')) == 1
            assert connection.scalar(text('SELECT COUNT(*) FROM consent_receipts')) == 0
            assert connection.scalar(text('SELECT COUNT(*) FROM product_photos')) == 0
            assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '0012_v014'
            assert {'product_photos', 'consent_receipts'} <= set(inspect(connection).get_table_names())
        command.check(config)
    finally:
        database.dispose()
