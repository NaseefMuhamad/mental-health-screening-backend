"""Check the configured database. Table creation is a separate explicit action.

Run from the backend root:
    python -m app.database.init_db --check

After models have been added and imported by app/models/__init__.py:
    python -m app.database.init_db --create-tables
"""

import argparse
import importlib
import sys

from sqlalchemy.exc import SQLAlchemyError

from app.database.base import Base
from app.database.connection import (
    DatabaseConfigurationError,
    check_database_connection,
    dispose_engine,
    get_engine,
)


def create_tables() -> list[str]:
    """Create missing registered model tables for initial local development.

    This does not create the PostgreSQL database, alter existing tables or insert
    users. Later schema changes must use Alembic migrations.
    """
    try:
        # The next folder step will explicitly export models from this package.
        importlib.import_module("app.models")
    except ModuleNotFoundError as error:
        if error.name == "app.models":
            raise DatabaseConfigurationError(
                "Models are not implemented yet. Run --check for now."
            ) from None
        raise

    if not Base.metadata.tables:
        raise DatabaseConfigurationError(
            "No model tables are registered. Import them in app/models/__init__.py first."
        )
    Base.metadata.create_all(bind=get_engine())
    return sorted(Base.metadata.tables)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check or initialize the screening database.")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--check", action="store_true", help="Test connectivity without changing data.")
    actions.add_argument("--create-tables", action="store_true", help="Create missing registered tables (local setup).")
    args = parser.parse_args(argv)

    try:
        if args.create_tables:
            names = create_tables()
            print(f"Registered tables ensured: {', '.join(names)}")
        else:
            check_database_connection()
            print("Database connection successful. No tables or records were changed.")
        return 0
    except DatabaseConfigurationError as error:
        print(f"Database configuration: {error}", file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print(
            "Database operation failed. Check PostgreSQL, credentials, database existence "
            "and permissions. Connection details have not been displayed.",
            file=sys.stderr,
        )
        return 1
    finally:
        dispose_engine()


if __name__ == "__main__":
    raise SystemExit(main())
