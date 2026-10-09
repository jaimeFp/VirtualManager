import os
import secrets
import uuid

from datetime import datetime, timezone
from typing import Any

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
)
from pydantic import BaseModel

from .database import Base, engine
from . import models

Base.metadata.create_all(bind=engine)


app = FastAPI(
    title="VirtualManager Central Server",
    version="0.1.0",
)
AGENT_TOKEN = os.environ.get("VIRTUALMANAGER_AGENT_TOKEN")

if not AGENT_TOKEN:
    raise RuntimeError("VIRTUALMANAGER_AGENT_TOKEN environment variable is not set.")


# ---------------------------------------------------------------------------
# Temporary in-memory storage
# ---------------------------------------------------------------------------

agents: dict[str, dict[str, Any]] = {}
commands: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# API models
# ---------------------------------------------------------------------------

class AgentRegistration(BaseModel):
    """!
    @brief Information required to register an agent.
    """
    agent_id: str
    hostname: str
    platform: str
    version: str


class VMInventory(BaseModel):
    """!
    @brief Virtual machine inventory reported by an agent.
    """
    vms: list[dict[str, Any]]


class CommandCreation(BaseModel):
    """!
    @brief Information required to create a virtual machine command.
    """
    agent_id: str
    vm_uuid: str
    action: str


class CommandResult(BaseModel):
    """!
    @brief Result of a command executed by an agent.
    """
    status: str
    error: str | None = None


def authenticate_agent(authorization: str | None = Header(default=None)) -> None:
    """!
    @brief Authenticate an agent using a Bearer token.
    @param authorization HTTP Authorization header.
    @exception HTTPException If authentication fails.
    """
    if authorization is None:
        raise HTTPException(status_code=401,detail="Authorization header missing.",)

    scheme, separator, token = authorization.partition(" ")

    if not separator or scheme.lower() != "bearer" or not secrets.compare_digest(token, AGENT_TOKEN):
        raise HTTPException(status_code=401,detail="Invalid authentication credentials.")

# ---------------------------------------------------------------------------
# Agent endpoints
# ---------------------------------------------------------------------------

@app.post("/api/v1/agents/register",dependencies=[Depends(authenticate_agent)])
def register_agent(agent: AgentRegistration) -> dict[str, str]:
    """!
    @brief Register or update an agent.
    @param agent Agent registration information.
    @return Registration result.
    """
    agents[agent.agent_id] = {
        "agent_id": agent.agent_id,
        "hostname": agent.hostname,
        "platform": agent.platform,
        "version": agent.version,
        "last_seen": datetime.now(timezone.utc).isoformat(),
        "vms": [],
    }

    return {"status": "registered","agent_id": agent.agent_id}


@app.get("/api/v1/agents")
def get_agents() -> list[dict[str, Any]]:
    """!
    @brief Get all registered agents.
    @return List of registered agents.
    """
    return list(agents.values())


@app.put("/api/v1/agents/{agent_id}/vms",dependencies=[Depends(authenticate_agent)])
def update_virtual_machines(agent_id: str,inventory: VMInventory) -> dict[str, str]:
    """!
    @brief Update the virtual machine inventory of an agent.
    @param agent_id Unique identifier of the agent.
    @param inventory Virtual machines reported by the agent.
    @return Update result.
    @exception HTTPException If the agent is not registered.
    """
    if agent_id not in agents:
        raise HTTPException(
            status_code=404,
            detail="Agent not registered.",
        )

    agents[agent_id]["vms"] = inventory.vms
    agents[agent_id]["last_seen"] = (
        datetime.now(timezone.utc).isoformat()
    )

    return {"status": "updated"}

@app.post(
    "/api/v1/agents/{agent_id}/commands/next",
    dependencies=[Depends(authenticate_agent)],
)
def get_next_command(
    agent_id: str,
) -> dict[str, Any] | None:
    """!
    @brief Get and claim the next pending command for an agent.
    @param agent_id Unique identifier of the agent.
    @return Claimed command or None if no command is pending.
    @exception HTTPException If the agent is not registered.
    """
    if agent_id not in agents:
        raise HTTPException(
            status_code=404,
            detail="Agent not registered.",
        )

    agents[agent_id]["last_seen"] = (
        datetime.now(timezone.utc).isoformat()
    )

    pending_command = next(
        (
            command
            for command in commands.values()
            if command["agent_id"] == agent_id
            and command["status"] == "pending"
        ),
        None,
    )

    if pending_command is None:
        return None

    pending_command["status"] = "running"
    pending_command["started_at"] = (
        datetime.now(timezone.utc).isoformat()
    )

    return pending_command
# ---------------------------------------------------------------------------
# Command endpoints
# ---------------------------------------------------------------------------

@app.post("/api/v1/commands")
def create_command(
    request: CommandCreation,
) -> dict[str, Any]:
    """!
    @brief Create a new command for an agent.
    @param request Command creation information.
    @return Created command information.
    @exception HTTPException If the target agent is not registered.
    """
    if request.agent_id not in agents:
        raise HTTPException(
            status_code=404,
            detail="Agent not registered.",
        )

    command_id = str(uuid.uuid4())

    command = {
        "id": command_id,
        "agent_id": request.agent_id,
        "vm_uuid": request.vm_uuid,
        "action": request.action,
        "status": "pending",
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "started_at": None,
        "completed_at": None,
    }

    commands[command_id] = command

    return command


@app.get("/api/v1/commands")
def get_all_commands() -> list[dict[str, Any]]:
    """!
    @brief Get all created commands.
    @return List of commands.
    """
    return list(commands.values())


@app.get("/api/v1/commands/{command_id}")
def get_command(
    command_id: str,
) -> dict[str, Any]:
    """!
    @brief Get information about a specific command.
    @param command_id Unique identifier of the command.
    @return Command information.
    @exception HTTPException If the command does not exist.
    """
    command = commands.get(command_id)

    if command is None:
        raise HTTPException(
            status_code=404,
            detail="Command not found.",
        )

    return command


@app.post(
    "/api/v1/commands/{command_id}/result",
    dependencies=[Depends(authenticate_agent)],
)
def report_command_result(
    command_id: str,
    result: CommandResult,
) -> dict[str, str]:
    """!
    @brief Store the result of an executed command.
    @param command_id Unique command identifier.
    @param result Command execution result.
    @return Update result.
    @exception HTTPException If the command does not exist, is not running,
                             or the result status is invalid.
    """
    command = commands.get(command_id)

    if command is None:
        raise HTTPException(
            status_code=404,
            detail="Command not found.",
        )

    if command["status"] != "running":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Command result cannot be reported from state "
                f"{command['status']!r}."
            ),
        )

    if result.status not in ("success", "failed"):
        raise HTTPException(
            status_code=400,
            detail="Command result must be 'success' or 'failed'.",
        )

    command["status"] = result.status
    command["error"] = result.error
    command["completed_at"] = (
        datetime.now(timezone.utc).isoformat()
    )

    return {
        "status": "updated",
    }