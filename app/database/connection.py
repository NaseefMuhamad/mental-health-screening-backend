"""Lazy PostgreSQL engine, request sessions and explicit transaction handling.

Importing this module does not connect to PostgreSQL or create any tables.
"""

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from functools import lru_cache
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session, sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class DatabaseConfigurationError(RuntimeError):
    """A safe configuration error that never includes database credentials."""


def database_url() -> URL:
    """Read DATABASE_URL, or build a URL from separate DB_* settings.

    Existing process environment variables take precedence over the root .env.
    URL.create handles special characters in a separate DB_PASSWORD correctly.
    """
    load_dotenv(PROJECT_ROOT / ".env", override=False, interpolate=False)
    raw_url = os.getenv("DATABASE_URL", "").strip()

    if raw_url:
        try:
            url = make_url(raw_url)
            # Validate the port here rather than exposing a raw parsing error later.
            _ = url.port
        except (ArgumentError, ValueError, TypeError):
            raise DatabaseConfigurationError(
                "DATABASE_URL is invalid. Check its format and encoded credentials."
            ) from None
        if url.drivername in {"postgresql", "postgres"}:
            url = url.set(drivername="postgresql+psycopg")
    else:
        database = os.getenv("DB_NAME", "").strip()
        username = os.getenv("DB_USER", "").strip()
        if not database or not username:
            raise DatabaseConfigurationError(
                "Set DATABASE_URL, or set DB_NAME and DB_USER in the backend .env."
            )
        try:
            port = int(os.getenv("DB_PORT", "5432"))
        except ValueError:
            raise DatabaseConfigurationError("DB_PORT must be a valid port number.") from None
        if not 1 <= port <= 65535:
            raise DatabaseConfigurationError("DB_PORT must be between 1 and 65535.")
        url = URL.create(
            drivername="postgresql+psycopg",
            username=username,
            password=os.getenv("DB_PASSWORD") or None,
            host=os.getenv("DB_HOST", "localhost").strip() or "localhost",
            port=port,
            database=database,
        )

    if url.drivername != "postgresql+psycopg":
        raise DatabaseConfigurationError(
            "Use PostgreSQL with the psycopg driver: postgresql+psycopg."
        )
    if url.port is not None and not 1 <= url.port <= 65535:
        raise DatabaseConfigurationError("The database port must be between 1 and 65535.")
    if not url.database or not url.username:
        raise DatabaseConfigurationError("The database name and database user are required.")
    return url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Create one pooled engine per process; connections open only when needed."""
    return create_engine(
        database_url(),
        pool_pre_ping=True,
        echo=False,
        hide_parameters=True,
        connect_args={"connect_timeout": 10},
    )


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """Reuse a factory, while creating a separate Session for each request."""
    return sessionmaker(
        bind=get_engine(),
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yield one session, roll back errors and always close.

    Successful requests are NOT automatically committed. Services must commit
    their write transaction deliberately before returning success.
    """
    session = get_session_factory()()
    try:
        yield session
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Commit a script's successful transaction; roll back failures and close.

    For a future command-line setup task, use `with session_scope() as db:`.
    Routes normally use get_db instead. Do not nest a second transaction owner
    around a Session that is already supplied by get_db.
    """
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def check_database_connection() -> None:
    """Execute SELECT 1 without changing data or exposing connection details."""
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1")).scalar_one()


def dispose_engine() -> None:
    """Release idle connections at shutdown; call after request work has ended."""
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_session_factory.cache_clear()
    get_engine.cache_clear()
