import json
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..database import get_database
from ..dependencies import require_agent, user_agent_ids, require_roles
from ..schemas import AgentRegistration, VMInventory
from ..security import (
    ENROLLMENT_TOKEN,
    authenticate_agent,
    bearer_token,
    token_digest,
)
from ..security import authenticate_user


router = APIRouter(prefix="/api/v1/agents", tags=["Agents"])


@router.post("/register")
def register_agent(
    agent: AgentRegistration,
    authorization: str | None = Header(default=None),
    database: Session = Depends(get_database),
) -> dict[str, str]:
    token = bearer_token(authorization)
    enrolled = secrets.compare_digest(token, ENROLLMENT_TOKEN)
    if not enrolled:
        credential = database.scalar(
            select(models.AgentCredential).where(models.AgentCredential.token_hash == token_digest(token))
        )
        if credential is None or credential.agent_id != agent.agent_id:
            raise HTTPException(status_code=401, detail="Invalid agent credential.")

    record = database.get(models.Agent, agent.agent_id)
    now = datetime.now(timezone.utc)
    if record is None:
        record = models.Agent(
            id=agent.agent_id,
            hostname=agent.hostname,
            platform=agent.platform,
            version=agent.version,
            last_seen=now,
        )
        database.add(record)
    else:
        record.hostname = agent.hostname
        record.platform = agent.platform
        record.version = agent.version
        record.last_seen = now
    credential = database.get(models.AgentCredential, agent.agent_id)
    issued_token = None
    if enrolled and credential is None:
        issued_token = secrets.token_urlsafe(32)
        database.add(models.AgentCredential(agent_id=agent.agent_id, token_hash=token_digest(issued_token)))
    elif enrolled and credential is not None:
        raise HTTPException(status_code=409, detail="Agent already enrolled. Use its saved credential or rotate it as administrator.")
    database.commit()
    response = {"status": "registered", "agent_id": agent.agent_id}
    if issued_token:
        response["agent_token"] = issued_token
    return response


@router.post("/{agent_id}/credential/rotate", dependencies=[Depends(require_roles("admin"))])
def rotate_agent_credential(agent_id: str, database: Session = Depends(get_database)) -> dict[str, str]:
    require_agent(agent_id, database)
    issued_token = secrets.token_urlsafe(32)
    credential = database.get(models.AgentCredential, agent_id)
    if credential is None:
        credential = models.AgentCredential(agent_id=agent_id, token_hash=token_digest(issued_token))
        database.add(credential)
    else:
        credential.token_hash = token_digest(issued_token)
        credential.created_at = datetime.now(timezone.utc)
    database.commit()
    return {"agent_id": agent_id, "agent_token": issued_token}


@router.get("")
def get_agents(
    user: models.WebUser = Depends(authenticate_user),
    database: Session = Depends(get_database),
) -> list[dict[str, Any]]:
    agents = database.scalars(select(models.Agent).order_by(models.Agent.hostname)).all()
    if user.role != "admin":
        permitted_agent_ids = set(user_agent_ids(database, user))
        agents = [agent for agent in agents if agent.id in permitted_agent_ids]
    result = []
    for agent in agents:
        vms = database.scalars(
            select(models.VirtualMachine).where(
                models.VirtualMachine.agent_id == agent.id,
                models.VirtualMachine.is_present.is_(True),
            )
        ).all()
        result.append({
            "agent_id": agent.id,
            "hostname": agent.hostname,
            "platform": agent.platform,
            "version": agent.version,
            "last_seen": agent.last_seen.isoformat(),
            "vms": [{
                "uuid": vm.uuid,
                "name": vm.name,
                "state": vm.state,
                "memory_mb": vm.memory_mb,
                "cpu_count": vm.cpu_count,
                "network_adapters": json.loads(vm.network_adapters or "[]"),
            } for vm in vms],
        })
    return result


@router.put("/{agent_id}/vms")
def update_virtual_machines(
    agent_id: str,
    inventory: VMInventory,
    authenticated_agent_id: str = Depends(authenticate_agent),
    database: Session = Depends(get_database),
) -> dict[str, str]:
    if authenticated_agent_id != agent_id:
        raise HTTPException(status_code=403, detail="Agent credentials cannot access another agent.")
    agent = require_agent(agent_id, database)
    known = database.scalars(
        select(models.VirtualMachine).where(models.VirtualMachine.agent_id == agent_id)
    ).all()
    by_uuid = {vm.uuid: vm for vm in known}
    for vm in known:
        vm.is_present = False

    for item in inventory.vms:
        vm_uuid = str(item.get("uuid", ""))
        name = item.get("name")
        state = item.get("state")
        if not vm_uuid or not isinstance(name, str) or not isinstance(state, str):
            raise HTTPException(status_code=422, detail="Each VM requires string uuid, name and state fields.")
        memory_mb = item.get("memory_mb")
        cpu_count = item.get("cpu_count")
        adapters = item.get("network_adapters", [])
        if memory_mb is not None and (not isinstance(memory_mb, int) or memory_mb < 1):
            raise HTTPException(status_code=422, detail="VM memory_mb must be a positive integer.")
        if cpu_count is not None and (not isinstance(cpu_count, int) or cpu_count < 1):
            raise HTTPException(status_code=422, detail="VM cpu_count must be a positive integer.")
        if not isinstance(adapters, list):
            raise HTTPException(status_code=422, detail="VM network_adapters must be a list.")
        vm = by_uuid.get(vm_uuid)
        if vm is None:
            vm = models.VirtualMachine(agent_id=agent_id, uuid=vm_uuid, name=name, state=state)
            database.add(vm)
        else:
            vm.name = name
            vm.state = state
            vm.is_present = True
        vm.memory_mb = memory_mb
        vm.cpu_count = cpu_count
        vm.network_adapters = json.dumps(adapters)

    agent.last_seen = datetime.now(timezone.utc)
    database.commit()
    return {"status": "updated"}


@router.post("/{agent_id}/commands/next")
def get_next_command(
    agent_id: str,
    authenticated_agent_id: str = Depends(authenticate_agent),
    database: Session = Depends(get_database),
) -> dict[str, Any] | None:
    if authenticated_agent_id != agent_id:
        raise HTTPException(status_code=403, detail="Agent credentials cannot access another agent.")
    require_agent(agent_id, database)
    command = database.scalar(
        select(models.Command)
        .where(models.Command.agent_id == agent_id, models.Command.status == "pending")
        .order_by(models.Command.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    agent = database.get(models.Agent, agent_id)
    agent.last_seen = datetime.now(timezone.utc)
    if command is None:
        database.commit()
        return None
    command.status = "running"
    command.started_at = datetime.now(timezone.utc)
    vm = database.get(models.VirtualMachine, command.vm_id)
    database.commit()
    return {
        "id": command.id,
        "agent_id": command.agent_id,
        "vm_uuid": vm.uuid,
        "action": command.action,
        "payload": json.loads(command.payload) if command.payload else None,
        "status": command.status,
        "created_at": command.created_at.isoformat(),
        "started_at": command.started_at.isoformat(),
    }
