"""Back up PostgreSQL or restore into a separate, empty database.

Credentials come from environment and are never placed in child process arguments.
Requires PostgreSQL 16 client tools in PATH or in --pg-bin.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


class OperationError(ValueError):
    """A message safe to expose without connection parameters or SQL."""


def connection(variable: str):
    raw = os.getenv(variable)
    if not raw:
        raise OperationError(f"Set {variable} in the environment")
    url = make_url(raw)
    if url.get_backend_name() != "postgresql" or not url.database or not url.host:
        raise OperationError(f"{variable} must be a PostgreSQL URL with host and database")
    return url


def pg_environment(url) -> dict[str, str]:
    env = os.environ.copy()
    # Remove inherited libpq routing/auth options before using the explicit URL.
    for key in tuple(env):
        if key.startswith("PG"):
            env.pop(key)
    env.update(
        PGHOST=url.host,
        PGPORT=str(url.port or 5432),
        PGDATABASE=url.database,
        PGUSER=url.username or "postgres",
        PGCONNECT_TIMEOUT="10",
    )
    if url.password is not None:
        env["PGPASSWORD"] = url.password
    option_variables = {
        "sslmode": "PGSSLMODE",
        "sslrootcert": "PGSSLROOTCERT",
        "sslcert": "PGSSLCERT",
        "sslkey": "PGSSLKEY",
        "channel_binding": "PGCHANNELBINDING",
    }
    if set(url.query) - option_variables.keys():
        raise OperationError("Unsupported connection option in database URL")
    for key, value in url.query.items():
        env[option_variables[key]] = str(value)
    return env


def executable(name: str, directory: Path | None) -> str:
    path = str(directory / name) if directory else name
    result = shutil.which(path)
    if not result:
        raise OperationError(f"Install PostgreSQL 16 client tools or supply --pg-bin ({name})")
    return result


def assert_empty(url) -> None:
    engine = create_engine(url, connect_args={"connect_timeout": 10})
    try:
        with engine.connect() as conn:
            count = conn.scalar(text("""
                SELECT COUNT(*) FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
                  AND n.nspname NOT LIKE 'pg_toast%'
                  AND n.nspname NOT LIKE 'pg_temp%'
                  AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
            """))
            if count:
                raise OperationError("Restore requires a separate empty database")
    finally:
        engine.dispose()


def database_identity(url) -> tuple:
    return (url.host.lower(), url.port or 5432, url.database)


def run(args: argparse.Namespace) -> None:
    if args.operation == "backup":
        url = connection("PETSHOP_DATABASE_URL")
        command = [executable("pg_dump", args.pg_bin), "--format=custom", "--no-password"]
        # Exclusive creation prevents accidental overwrites. A failed dump stays
        # under the requested name; callers must honor the nonzero exit status.
        with args.file.open("xb") as output:
            result = subprocess.run(command, env=pg_environment(url), stdout=output,
                                    stderr=subprocess.PIPE, check=False)
    else:
        source = connection("PETSHOP_DATABASE_URL")
        target = connection("PETSHOP_RESTORE_DATABASE_URL")
        if database_identity(source) == database_identity(target):
            raise OperationError("Restore target must differ from the source database")
        target_env = pg_environment(target)
        assert_empty(target)
        command = [executable("pg_restore", args.pg_bin), "--exit-on-error",
                   "--single-transaction", "--no-owner", "--no-privileges",
                   "--no-password", "--dbname", target.database]
        with args.file.open("rb") as source_file:
            result = subprocess.run(command, env=target_env, stdin=source_file,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        # PostgreSQL stderr can contain values or SQL from a database; redact it.
        raise OperationError(f"{args.operation} failed (PostgreSQL exit {result.returncode})")
    print(json.dumps({"event": f"database_{args.operation}_succeeded", "file": str(args.file)}))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("backup", "restore"))
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--pg-bin", type=Path)
    args = parser.parse_args()
    try:
        run(args)
    except Exception as exc:
        # Driver exceptions can embed URLs/SQL. Print only safe own messages.
        safe = str(exc) if isinstance(exc, OperationError) else type(exc).__name__
        print(json.dumps({"event": "database_operation_failed", "reason": safe}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
