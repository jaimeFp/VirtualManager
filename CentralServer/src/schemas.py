from typing import Any

from pydantic import BaseModel, Field


class AgentRegistration(BaseModel):
    agent_id: str
    hostname: str
    platform: str
    version: str


class VMInventory(BaseModel):
    vms: list[dict[str, Any]]


class CommandCreation(BaseModel):
    agent_id: str
    vm_uuid: str
    action: str
    payload: dict[str, Any] | None = None


class CommandResult(BaseModel):
    status: str
    error: str | None = None


class LoginCredentials(BaseModel):
    username: str
    password: str


class UserCreation(BaseModel):
    username: str
    password: str
    role: str
    agent_ids: list[str] = Field(default_factory=list)


class UserUpdate(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    agent_ids: list[str] | None = None
