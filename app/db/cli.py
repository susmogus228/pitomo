"""Explicit empty database initialization without the historical demo seed."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.auth import rate_limit as _rate_limit  # noqa: F401
from app.db import models as _models  # noqa: F401
from app.db.base import Base
from app.db.seed import seed_demo_catalog
from app.db.pitomo_seed import seed_pitomo_catalog, refresh_demo_metadata
from app.db.session import Database


def initialize_database(url: str, *, seed: bool = False) -> None:
    database = Database(url)
    try:
        with database.engine.begin() as connection:
            if inspect(connection).get_table_names():
                raise RuntimeError('Initialization requires an empty database; use alembic upgrade head for existing data')
            if connection.dialect.name == 'sqlite':
                connection.exec_driver_sql('BEGIN IMMEDIATE')
            Base.metadata.create_all(connection)
            config = Config(str(Path(__file__).resolve().parents[2] / 'alembic.ini'))
            config.attributes['connection'] = connection
            command.stamp(config, 'head')
        if seed:
            with database.session_factory.begin() as session:
                seed_demo_catalog(session)
    finally:
        database.dispose()


def upgrade_database(url: str) -> None:
    database = Database(url)
    try:
        with database.engine.connect() as connection:
            empty = not inspect(connection).get_table_names()
        if empty:
            initialize_database(url)
        else:
            config = Config(str(Path(__file__).resolve().parents[2] / 'alembic.ini'))
            config.attributes['database_url'] = url
            command.upgrade(config, 'head')
    finally:
        database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init', 'upgrade', 'seed', 'seed-pitomo', 'refresh-demo-metadata'])
    parser.add_argument('--seed', action='store_true', help='Explicitly insert the demonstration catalog')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--dry-run', action='store_true', help='Preview metadata changes without writes (default)')
    modes.add_argument('--apply', action='store_true', help='Explicitly apply known demonstration metadata changes')
    args = parser.parse_args()
    if (args.apply or args.dry_run) and args.command != 'refresh-demo-metadata':
        parser.error('--apply and --dry-run are supported only with refresh-demo-metadata')
    url = os.getenv('PETSHOP_DATABASE_URL')
    if not url:
        parser.error('PETSHOP_DATABASE_URL is required')
    if args.seed and args.command != 'init':
        parser.error('--seed is supported only with init')
    if args.command == 'init':
        initialize_database(url, seed=args.seed)
    elif args.command == 'upgrade':
        upgrade_database(url)
    else:
        database = Database(url)
        try:
            with database.session_factory.begin() as session:
                if args.command == 'seed-pitomo':
                    count = seed_pitomo_catalog(session)
                    print(f'Pitomo demonstration products added: {count}')
                elif args.command == 'refresh-demo-metadata':
                    report = refresh_demo_metadata(session, apply=args.apply)
                    print(json.dumps(report, ensure_ascii=False))
                elif not seed_demo_catalog(session):
                    parser.error('Demo seed requires an empty catalog; existing products were preserved')
        finally:
            database.dispose()


if __name__ == '__main__':
    main()
