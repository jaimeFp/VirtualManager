import hashlib
import os
import re
import secrets
import time

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .database import get_database


ENROLLMENT_TOKEN = os.environ.get("VIRTUALMANAGER_ENROLLMENT_TOKEN")
WEB_SESSION_COOKIE = "vm_session"
WEB_SESSION_TTL = 8 * 60 * 60

if not ENROLLMENT_TOKEN:
    raise RuntimeError("VIRTUALMANAGER_ENROLLMENT_TOKEN must be set.")


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 600_000)
    return f"pbkdf2_sha256$600000${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds))
        return secrets.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def password_is_secure(password: str) -> bool:
    return (
        len(password) >= 12
        and re.search(r"[a-z]", password) is not None
        and re.search(r"[A-Z]", password) is not None
        and re.search(r"\d", password) is not None
        and re.search(r"[^A-Za-z0-9]", password) is not None
    )


DUMMY_PASSWORD_HASH = hash_password("constant-time-placeholder", b"virtualmanagerdummy")


def authenticate_user(
    request: Request,
    database: Session = Depends(get_database),
) -> models.WebUser:
    token = request.cookies.get(WEB_SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Login required.")
    session_record = database.get(models.WebSession, token_digest(token))
    if session_record is None:
        raise HTTPException(status_code=401, detail="Session expired.")
    if session_record.expires_at <= int(time.time()):
        database.delete(session_record)
        database.commit()
        raise HTTPException(status_code=401, detail="Session expired.")
    user = database.get(models.WebUser, session_record.user_id)
    if user is None or not user.is_active:
        database.delete(session_record)
        database.commit()
        raise HTTPException(status_code=401, detail="Login required.")
    return user


def bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise HTTPException(status_code=401, detail="Authorization header missing.")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials.")
    return token


def authenticate_agent(
    authorization: str | None = Header(default=None),
    database: Session = Depends(get_database),
) -> str:
    token_hash = token_digest(bearer_token(authorization))
    credential = database.scalar(
        select(models.AgentCredential).where(models.AgentCredential.token_hash == token_hash)
    )
    if credential is None:
        raise HTTPException(status_code=401, detail="Invalid agent credential.")
    return credential.agent_id
