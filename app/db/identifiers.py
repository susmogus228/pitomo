"""Allocate IDs inside the caller's transaction without SQLite MAX(id) reuse."""
from sqlalchemy import func, select, text
from sqlalchemy.dialects.sqlite import insert

from .models import IdCounterORM


def next_id(session, model):
    table = model.__tablename__
    if session.get_bind().dialect.name == 'postgresql':
        return int(session.scalar(text("SELECT nextval(pg_get_serial_sequence(:table, 'id'))"), {'table': table}))
    maximum = select(func.coalesce(func.max(model.id), 0)).scalar_subquery()
    statement = insert(IdCounterORM).values(name=table, value=maximum + 1)
    statement = statement.on_conflict_do_update(
        index_elements=['name'], set_={'value': func.max(IdCounterORM.value, maximum) + 1},
    ).returning(IdCounterORM.value)
    return int(session.scalar(statement))
