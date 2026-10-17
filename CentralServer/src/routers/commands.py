import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..database import get_database
from ..dependencies import require_agent, require_agent_access, require_roles, user_agent_ids
from ..schemas import CommandCreation, CommandResult
from ..security import authenticate_agent, authenticate_user


router = APIRouter(prefix="/api/v1/commands", tags=["Commands"])
ALLOWED_ACTIONS = {"start", "pause", "resume", "shutdown", "poweroff", "configure"}
NETWORK_MODES = {"none", "null", "nat", "natnetwork", "bridged", "intnet", "hostonly", "generic"}


def validate_configuration(payload: dict[str, Any] | None) -> None:
    payload = payload or {}
    if type(payload.get("memory_mb")) is not int or not 4 <= payload["memory_mb"] <= 1_048_576:
        raise HTTPException(status_code=422, detail="La memoria debe estar entre 4 y 1 048 576 MB.")
    if type(payload.get("cpu_count")) is not int or not 1 <= payload["cpu_count"] <= 256:
        raise HTTPException(status_code=422, detail="Los núcleos deben estar entre 1 y 256.")
    adapters = payload.get("network_adapters")
    if not isinstance(adapters, list) or len(adapters) != 8:
        raise HTTPException(status_code=422, detail="Debes especificar las ocho interfaces de red.")
    for index, adapter in enumerate(adapters, 1):
        if (not isinstance(adapter, dict) or adapter.get("slot") != index
                or not isinstance(adapter.get("enabled"), bool)
                or adapter.get("mode") not in NETWORK_MODES
                or not isinstance(adapter.get("adapter", ""), str)
                or len(adapter.get("adapter", "")) > 255):
            raise HTTPException(status_code=422, detail="La configuración de interfaces de red no es válida.")


def command_as_dict(command: models.Command, vm_uuid: str) -> dict[str, Any]:
    return {
        "id": command.id,
        "agent_id": command.agent_id,
        "vm_uuid": vm_uuid,
        "action": command.action,
        "status": command.status,
        "error": command.error,
        "created_at": command.created_at.isoformat(),
        "started_at": command.started_at.isoformat() if command.started_at else None,
        "completed_at": command.completed_at.isoformat() if command.completed_at else None,
    }


@router.post("")
def create_command(
    request: CommandCreation,
    user: models.WebUser = Depends(require_roles("admin", "operator")),
    database: Session = Depends(get_database),
) -> dict[str, Any]:
    require_agent_access(database, user, request.agent_id)
    require_agent(request.agent_id, database)
    vm = database.scalar(select(models.VirtualMachine).where(
        models.VirtualMachine.agent_id == request.agent_id,
        models.VirtualMachine.uuid == request.vm_uuid,
        models.VirtualMachine.is_present.is_(True),
    ))
    if vm is None:
        raise HTTPException(status_code=404, detail="Virtual machine not found for this agent.")
    if request.action not in ALLOWED_ACTIONS:
        raise HTTPException(status_code=422, detail="Unsupported virtual machine action.")
    if request.action == "configure":
        if vm.state != "poweroff":
            raise HTTPException(status_code=409, detail="Apaga la máquina virtual antes de cambiar sus recursos.")
        validate_configuration(request.payload)

    command = models.Command(
        id=str(uuid.uuid4()),
        agent_id=request.agent_id,
        vm_id=vm.id,
        action=request.action,
        payload=json.dumps(request.payload) if request.payload is not None else None,
        status="pending",
    )
    database.add(command)
    database.commit()
    database.refresh(command)
    return {
        "id": command.id,
        "agent_id": command.agent_id,
        "vm_uuid": vm.uuid,
        "action": command.action,
        "status": command.status,
        "error": command.error,
        "created_at": command.created_at.isoformat(),
        "started_at": None,
        "completed_at": None,
    }


@router.get("")
def get_all_commands(
    agent_id: str | None = Query(default=None),
    vm_uuid: str | None = Query(default=None),
    user: models.WebUser = Depends(authenticate_user),
    database: Session = Depends(get_database),
) -> list[dict[str, Any]]:
    statement = select(models.Command, models.VirtualMachine.uuid).join(
        models.VirtualMachine, models.Command.vm_id == models.VirtualMachine.id
    )
    if agent_id:
        require_agent_access(database, user, agent_id)
        statement = statement.where(models.Command.agent_id == agent_id)
    elif user.role != "admin":
        permitted_agent_ids = user_agent_ids(database, user)
        if not permitted_agent_ids:
            return []
        statement = statement.where(models.Command.agent_id.in_(permitted_agent_ids))
    if vm_uuid:
        statement = statement.where(models.VirtualMachine.uuid == vm_uuid)
    rows = database.execute(statement.order_by(models.Command.created_at.desc())).all()
    return [command_as_dict(command, machine_uuid) for command, machine_uuid in rows]


@router.get("/{command_id}")
def get_command(
    command_id: str,
    user: models.WebUser = Depends(authenticate_user),
    database: Session = Depends(get_database),
) -> dict[str, Any]:
    command = database.get(models.Command, command_id)
    if command is None:
        raise HTTPException(status_code=404, detail="Command not found.")
    require_agent_access(database, user, command.agent_id)
    vm = database.get(models.VirtualMachine, command.vm_id)
    return command_as_dict(command, vm.uuid)


@router.post("/{command_id}/result")
def report_command_result(
    command_id: str,
    result: CommandResult,
    authenticated_agent_id: str = Depends(authenticate_agent),
    database: Session = Depends(get_database),
) -> dict[str, str]:
    command = database.get(models.Command, command_id)
    if command is None:
        raise HTTPException(status_code=404, detail="Command not found.")
    if command.agent_id != authenticated_agent_id:
        raise HTTPException(status_code=403, detail="Agent credentials cannot report another agent's command.")
    if command.status != "running":
        raise HTTPException(status_code=409, detail=f"Command result cannot be reported from state {command.status!r}.")
    if result.status not in ("success", "failed"):
        raise HTTPException(status_code=400, detail="Command result must be 'success' or 'failed'.")
    command.status = result.status
    command.error = result.error
    command.completed_at = datetime.now(timezone.utc)
    database.commit()
    return {"status": "updated"}
