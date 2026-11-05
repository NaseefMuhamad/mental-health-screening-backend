"""One-time local setup. No public administrator signup endpoint is exposed."""

import argparse
from getpass import getpass
import sys

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.database.connection import DatabaseConfigurationError, dispose_engine, get_session_factory
from app.schemas.user import BootstrapAdmin
from app.services.auth_service import bootstrap_admin
from app.services.errors import ServiceError


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the first institution administrator.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    password = getpass("New administrator password (12–128 characters): ")
    if password != getpass("Confirm password: "):
        print("Passwords do not match.", file=sys.stderr)
        return 1
    try:
        payload = BootstrapAdmin(email=args.email, name=args.name, password=password)
        with get_session_factory()() as db:
            user = bootstrap_admin(db, payload)
        print(f"Administrator created: {user.email} ({user.id}). Sign in through /auth/login.")
        return 0
    except ValidationError:
        print("Check the name, email and password length. No account was created.", file=sys.stderr)
    except (ServiceError, DatabaseConfigurationError) as error:
        print(str(error), file=sys.stderr)
    except SQLAlchemyError:
        print("Database operation failed. Check configuration and initialize the tables first.", file=sys.stderr)
    finally:
        dispose_engine()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
