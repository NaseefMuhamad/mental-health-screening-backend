"""Environment settings without importing or connecting to the database."""

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


@dataclass(frozen=True)
class AuthSettings:
    session_minutes: int
    invitation_hours: int
    cors_origins: tuple[str, ...]


@lru_cache(maxsize=1)
def get_settings() -> AuthSettings:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False, interpolate=False)
    try:
        minutes = int(os.getenv("AUTH_SESSION_MINUTES", "30"))
        hours = int(os.getenv("INVITATION_HOURS", "24"))
    except ValueError:
        raise RuntimeError("Auth expiry settings must be integer values.") from None
    if not 5 <= minutes <= 1440 or not 1 <= hours <= 168:
        raise RuntimeError("Session minutes must be 5–1440; invitation hours must be 1–168.")
    origins = tuple(part.strip() for part in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",") if part.strip())
    for origin in origins:
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username is not None or "*" in origin:
            raise RuntimeError("CORS_ORIGINS must contain explicit HTTP(S) origins without paths or wildcards.")
    return AuthSettings(minutes, hours, origins)
