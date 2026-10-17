import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import models
from ..database import get_database
from ..dependencies import require_roles, user_agent_ids
from ..schemas import UserCreation, UserUpdate
from ..security import authenticate_user, hash_password, password_is_secure


router = APIRouter(prefix="/api/v1/users", tags=["Users"])


def user_as_dict(user: models.WebUser, database: Session) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat(),
        "agent_ids": user_agent_ids(database, user),
    }


@router.get("", dependencies=[Depends(require_roles("admin"))])
def list_users(database: Session = Depends(get_database)) -> list[dict[str, Any]]:
    users = database.scalars(select(models.WebUser).order_by(models.WebUser.username)).all()
    return [user_as_dict(user, database) for user in users]


@router.post("", dependencies=[Depends(require_roles("admin"))], status_code=201)
def create_user(request: UserCreation, database: Session = Depends(get_database)) -> dict[str, Any]:
    username = request.username.strip().lower()
    if not re.fullmatch(r"[a-z0-9_.-]{3,80}", username):
        raise HTTPException(status_code=422, detail="Use 3–80 letters, numbers, dots, underscores or hyphens for the username.")
    if not password_is_secure(request.password):
        raise HTTPException(status_code=422, detail="The initial password must have at least 12 characters and include uppercase and lowercase letters, a number and a symbol.")
    if request.role not in {"admin", "operator", "observer"}:
        raise HTTPException(status_code=422, detail="Role must be admin, operator or observer.")
    requested_agent_ids = list(dict.fromkeys(request.agent_ids))
    if request.role != "admin" and requested_agent_ids:
        known_agent_ids = set(database.scalars(
            select(models.Agent.id).where(models.Agent.id.in_(requested_agent_ids))
        ).all())
        if known_agent_ids != set(requested_agent_ids):
            raise HTTPException(status_code=422, detail="One or more selected agents do not exist.")
    if database.scalar(select(models.WebUser.id).where(models.WebUser.username == username)):
        raise HTTPException(status_code=409, detail="That username already exists.")

    user = models.WebUser(
        username=username,
        password_hash=hash_password(request.password),
        role=request.role,
        is_active=True,
    )
    database.add(user)
    database.flush()
    if request.role != "admin":
        database.add_all([
            models.WebUserAgentAccess(user_id=user.id, agent_id=agent_id)
            for agent_id in requested_agent_ids
        ])
    database.commit()
    database.refresh(user)
    return user_as_dict(user, database)


@router.patch("/{user_id}", dependencies=[Depends(require_roles("admin"))])
def update_user(
    user_id: str,
    request: UserUpdate,
    current: models.WebUser = Depends(authenticate_user),
    database: Session = Depends(get_database),
) -> dict[str, Any]:
    user = database.get(models.WebUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    fields = request.model_fields_set
    role = request.role if "role" in fields else user.role
    is_active = request.is_active if "is_active" in fields else user.is_active
    agent_ids = request.agent_ids if "agent_ids" in fields else None
    if role is not None and role not in {"admin", "operator", "observer"}:
        raise HTTPException(status_code=422, detail="Role must be admin, operator or observer.")
    if is_active is None:
        is_active = user.is_active
    if agent_ids is not None:
        agent_ids = list(dict.fromkeys(agent_ids))
        known_agent_ids = set(database.scalars(select(models.Agent.id).where(models.Agent.id.in_(agent_ids))).all()) if agent_ids else set()
        if known_agent_ids != set(agent_ids):
            raise HTTPException(status_code=422, detail="One or more selected agents do not exist.")
    if current.id == user.id and (role != user.role or not is_active):
        raise HTTPException(status_code=409, detail="You cannot remove administrator access from your own account.")
    if user.role == "admin" and user.is_active and (role != "admin" or not is_active):
        active_admins = database.scalars(
            select(models.WebUser.id).where(models.WebUser.role == "admin", models.WebUser.is_active.is_(True))
        ).all()
        if len(active_admins) <= 1:
            raise HTTPException(status_code=409, detail="At least one active administrator is required.")

    previous_agent_ids = set(user_agent_ids(database, user))
    next_agent_ids = (set(agent_ids) if agent_ids is not None else previous_agent_ids) if role != "admin" else set()
    agent_access_changed = previous_agent_ids != next_agent_ids
    access_changed = role != user.role or is_active != user.is_active
    user.role = role or user.role
    user.is_active = is_active
    if agent_ids is not None or user.role == "admin":
        database.execute(delete(models.WebUserAgentAccess).where(models.WebUserAgentAccess.user_id == user.id))
        if user.role != "admin":
            database.add_all([
                models.WebUserAgentAccess(user_id=user.id, agent_id=agent_id)
                for agent_id in (agent_ids or [])
            ])
    if access_changed or agent_access_changed:
        database.execute(delete(models.WebSession).where(models.WebSession.user_id == user.id))
    database.commit()
    database.refresh(user)
    return user_as_dict(user, database)
