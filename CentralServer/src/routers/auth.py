import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import models
from ..database import get_database
from ..schemas import LoginCredentials
from ..security import (
    DUMMY_PASSWORD_HASH,
    WEB_SESSION_COOKIE,
    WEB_SESSION_TTL,
    authenticate_user,
    token_digest,
    verify_password,
)


router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post("/login")
def login(
    credentials: LoginCredentials,
    response: Response,
    database: Session = Depends(get_database),
) -> dict[str, str]:
    username = credentials.username.strip().lower()
    user = database.scalar(select(models.WebUser).where(models.WebUser.username == username))
    valid = verify_password(credentials.password, user.password_hash if user else DUMMY_PASSWORD_HASH)
    if not valid or user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")

    now = int(time.time())
    database.execute(delete(models.WebSession).where(models.WebSession.expires_at <= now))
    session_token = secrets.token_urlsafe(32)
    database.add(models.WebSession(
        token_hash=token_digest(session_token),
        user_id=user.id,
        expires_at=now + WEB_SESSION_TTL,
    ))
    database.commit()
    response.set_cookie(
        key=WEB_SESSION_COOKIE,
        value=session_token,
        max_age=WEB_SESSION_TTL,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/api/v1",
    )
    return {"id": user.id, "username": user.username, "role": user.role}


@router.get("/me")
def current_user(user: models.WebUser = Depends(authenticate_user)) -> dict[str, str]:
    return {"id": user.id, "username": user.username, "role": user.role}


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    database: Session = Depends(get_database),
) -> dict[str, str]:
    token = request.cookies.get(WEB_SESSION_COOKIE)
    if token:
        session_record = database.get(models.WebSession, token_digest(token))
        if session_record is not None:
            database.delete(session_record)
            database.commit()
    response.delete_cookie(
        key=WEB_SESSION_COOKIE,
        path="/api/v1",
        secure=True,
        httponly=True,
        samesite="strict",
    )
    return {"status": "logged_out"}
