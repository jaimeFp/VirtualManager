from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .database import get_database
from .security import authenticate_user


def require_roles(*allowed_roles: str):
    def dependency(user: models.WebUser = Depends(authenticate_user)) -> models.WebUser:
        if user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Your account does not have permission for this action.")
        return user
    return dependency


def user_agent_ids(database: Session, user: models.WebUser) -> list[str]:
    return list(database.scalars(
        select(models.WebUserAgentAccess.agent_id).where(
            models.WebUserAgentAccess.user_id == user.id
        )
    ).all())


def require_agent_access(database: Session, user: models.WebUser, agent_id: str) -> None:
    if user.role != "admin" and agent_id not in user_agent_ids(database, user):
        raise HTTPException(status_code=403, detail="Your account does not have access to this agent.")


def require_agent(agent_id: str, database: Session) -> models.Agent:
    agent = database.get(models.Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not registered.")
    return agent
