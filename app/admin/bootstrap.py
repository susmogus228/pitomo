"""Create or promote an administrator; passwords never enter command arguments."""
from __future__ import annotations

import argparse
import getpass
import sys

from app.auth.schemas import RegistrationIdentity
from app.core.config import load_settings
from app.core.security import hash_password
from app.db.session import Database
from app.users.models import User
from app.users.repository import SQLAlchemyUserRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Create or promote a Petshop administrator')
    parser.add_argument('--email', required=True)
    parser.add_argument('--password-stdin', action='store_true', help='Read one password line from standard input')
    parser.add_argument('--first-name', required=True)
    parser.add_argument('--last-name', default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.password_stdin:
        password = sys.stdin.readline().rstrip('\r\n')
    else:
        password = getpass.getpass('Admin password: ')
        if password != getpass.getpass('Confirm password: '):
            raise SystemExit('Passwords do not match')
    try:
        # Local owner provisioning is not a customer's registration or consent.
        data = RegistrationIdentity(email=args.email, password=password, first_name=args.first_name, last_name=args.last_name)
    except ValueError:
        raise SystemExit('Invalid administrator data: check email, names and password length (8-128)') from None
    settings = load_settings()
    settings.validate()
    database = Database(settings.database_url, echo=False)
    try:
        with database.session_factory() as session:
            repository = SQLAlchemyUserRepository(session)
            user = repository.get_by_email(data.email)
            if user is None:
                user = User(id=repository.next_user_id(), email=data.email,
                            password_hash=hash_password(data.password), first_name=data.first_name,
                            last_name=data.last_name, role='admin', is_active=True)
                repository.add(user)
                action = 'created'
            else:
                user.change_role('admin')
                user.set_active(True)
                user.change_password_hash(hash_password(data.password))
                user.change_first_name(data.first_name)
                user.change_last_name(data.last_name)
                repository.save(user, fields={'role', 'is_active', 'password_hash', 'first_name', 'last_name'})
                action = 'promoted'
            session.commit()
        print(f'Admin {action}: id={user.id}')
    finally:
        database.dispose()


if __name__ == '__main__':
    main()
