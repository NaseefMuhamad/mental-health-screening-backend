"""Argon2 password hashing and random, hashed-at-rest bearer credentials."""

import hashlib
import secrets

from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError


password_hasher = PasswordHash.recommended()
_DUMMY_HASH = password_hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        valid = password_hasher.verify(password, password_hash or _DUMMY_HASH)
    except (ValueError, UnknownHashError):
        return False
    return bool(password_hash) and valid


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
