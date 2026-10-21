"""Translate only expected unique constraints; preserve unexpected DB errors."""
from sqlalchemy.exc import IntegrityError


def unique_violation(exc: IntegrityError, *, names: set[str], sqlite_columns: set[str]) -> bool:
    diagnostic = getattr(exc.orig, 'diag', None)
    if diagnostic is not None:
        return getattr(exc.orig, 'sqlstate', None) == '23505' and diagnostic.constraint_name in names
    message = str(exc.orig)
    return message.startswith('UNIQUE constraint failed: ') and message.removeprefix('UNIQUE constraint failed: ') in sqlite_columns
