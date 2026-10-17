import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .database import engine
from .security import hash_password


def bootstrap_admin() -> None:
    username = os.environ.get("VIRTUALMANAGER_WEB_USERNAME", "").strip().lower()
    password = os.environ.get("VIRTUALMANAGER_WEB_PASSWORD", "")
    if not username or not password:
        raise RuntimeError("VIRTUALMANAGER_WEB_USERNAME and VIRTUALMANAGER_WEB_PASSWORD must be set.")
    if len(password) < 12:
        raise RuntimeError("VIRTUALMANAGER_WEB_PASSWORD must contain at least 12 characters.")

    with Session(engine) as database:
        if database.scalar(select(models.WebUser.id).limit(1)) is None:
            database.add(models.WebUser(
                username=username,
                password_hash=hash_password(password),
                role="admin",
                is_active=True,
            ))
            database.commit()
            return

        active_admin_exists = database.scalar(
            select(models.WebUser.id).where(
                models.WebUser.role == "admin",
                models.WebUser.is_active.is_(True),
            ).limit(1)
        )
        if active_admin_exists is None:
            bootstrap_user = database.scalar(
                select(models.WebUser).where(models.WebUser.username == username)
            )
            if bootstrap_user is not None:
                bootstrap_user.role = "admin"
                bootstrap_user.is_active = True
                database.commit()
