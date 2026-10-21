"""Alembic environment configured from PETSHOP_DATABASE_URL."""
from __future__ import annotations

from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.db.base import Base
from app.db import models as _models  # noqa: F401
from app.auth import rate_limit as _rate_limit  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

url = config.attributes.get('database_url') or os.getenv('PETSHOP_DATABASE_URL')
if not url:
    external_connection = config.attributes.get('connection')
    if external_connection is not None:
        url = external_connection.engine.url.render_as_string(hide_password=False)
    else:
        raise RuntimeError('PETSHOP_DATABASE_URL or an explicit migration connection is required')
config.set_main_option('sqlalchemy.url', url.replace('%', '%%'))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def migrate_connection(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    external = config.attributes.get('connection')
    if external is not None:
        migrate_connection(external)
        return
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}), prefix='sqlalchemy.', poolclass=pool.NullPool,
    )
    try:
        with connectable.connect() as connection:
            if connection.dialect.name == 'sqlite':
                # Rebuilding referenced tables requires FK enforcement off only
                # on this migration connection. Validate all references before
                # committing, then restore enforcement for this connection.
                connection.exec_driver_sql('PRAGMA foreign_keys=OFF')
                connection.commit()
                connection.exec_driver_sql('BEGIN IMMEDIATE')
                try:
                    migrate_connection(connection)
                    if connection.exec_driver_sql('PRAGMA foreign_key_check').first() is not None:
                        raise RuntimeError('Migration introduced invalid foreign keys')
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
                finally:
                    connection.exec_driver_sql('PRAGMA foreign_keys=ON')
            else:
                migrate_connection(connection)
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
