import hashlib
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .database import Base, engine, get_database
from . import models


# Create missing tables for a fresh development installation. Existing schemas
# should be upgraded with a migration when Alembic is introduced.
Base.metadata.create_all(bind=engine)

app = FastAPI(title="VirtualManager Central Server", version="0.1.0")
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")
app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")
ADMIN_TOKEN = os.environ.get("VIRTUALMANAGER_ADMIN_TOKEN")
ENROLLMENT_TOKEN = os.environ.get("VIRTUALMANAGER_ENROLLMENT_TOKEN")
WEB_USERNAME = os.environ.get("VIRTUALMANAGER_WEB_USERNAME", "").strip().lower()
WEB_PASSWORD = os.environ.get("VIRTUALMANAGER_WEB_PASSWORD", "")
WEB_SESSION_COOKIE = "vm_session"
WEB_SESSION_TTL = 8 * 60 * 60

if not ADMIN_TOKEN or not ENROLLMENT_TOKEN:
    raise RuntimeError("VIRTUALMANAGER_ADMIN_TOKEN and VIRTUALMANAGER_ENROLLMENT_TOKEN must be set.")
if secrets.compare_digest(ADMIN_TOKEN, ENROLLMENT_TOKEN):
    raise RuntimeError("Admin and enrollment credentials must be different.")
if not WEB_USERNAME or not WEB_PASSWORD:
    raise RuntimeError("VIRTUALMANAGER_WEB_USERNAME and VIRTUALMANAGER_WEB_PASSWORD must be set.")
if len(WEB_PASSWORD) < 12:
    raise RuntimeError("VIRTUALMANAGER_WEB_PASSWORD must contain at least 12 characters.")


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


DUMMY_PASSWORD_HASH = hash_password("constant-time-placeholder", b"virtualmanagerdummy")

with Session(engine) as bootstrap_database:
    if bootstrap_database.scalar(select(models.WebUser.id).limit(1)) is None:
        bootstrap_database.add(models.WebUser(username=WEB_USERNAME, password_hash=hash_password(WEB_PASSWORD)))
        bootstrap_database.commit()


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


class CommandResult(BaseModel):
    status: str
    error: str | None = None


class LoginCredentials(BaseModel):
    username: str
    password: str


@app.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


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
    if user is None:
        raise HTTPException(status_code=401, detail="Login required.")
    return user


@app.post("/api/v1/auth/login")
def login(
    credentials: LoginCredentials,
    response: Response,
    database: Session = Depends(get_database),
) -> dict[str, str]:
    username = credentials.username.strip().lower()
    user = database.scalar(select(models.WebUser).where(models.WebUser.username == username))
    # Run the same password KDF for unknown users to reduce username timing leaks.
    valid = verify_password(credentials.password, user.password_hash if user else DUMMY_PASSWORD_HASH)
    if not valid or user is None:
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
    return {"username": user.username}


@app.get("/api/v1/auth/me")
def current_user(user: models.WebUser = Depends(authenticate_user)) -> dict[str, str]:
    return {"username": user.username}


@app.post("/api/v1/auth/logout")
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


def bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise HTTPException(status_code=401, detail="Authorization header missing.")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials.")
    return token


def authenticate_admin(authorization: str | None = Header(default=None)) -> None:
    token = bearer_token(authorization)
    if not secrets.compare_digest(token, ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid authentication credentials.")


def authenticate_agent(
    authorization: str | None = Header(default=None),
    database: Session = Depends(get_database),
) -> str:
    """Validate an agent-scoped credential and return its agent id."""
    token_hash = hashlib.sha256(bearer_token(authorization).encode("utf-8")).hexdigest()
    credential = database.scalar(
        select(models.AgentCredential).where(models.AgentCredential.token_hash == token_hash)
    )
    if credential is None:
        raise HTTPException(status_code=401, detail="Invalid agent credential.")
    return credential.agent_id


def require_agent(agent_id: str, database: Session) -> models.Agent:
    agent = database.get(models.Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not registered.")
    return agent


@app.post("/api/v1/agents/register")
def register_agent(
    agent: AgentRegistration,
    authorization: str | None = Header(default=None),
    database: Session = Depends(get_database),
) -> dict[str, str]:
    token = bearer_token(authorization)
    enrolled = secrets.compare_digest(token, ENROLLMENT_TOKEN)
    if not enrolled:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        credential = database.scalar(
            select(models.AgentCredential).where(models.AgentCredential.token_hash == token_hash)
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
    issued_token = None
    credential = database.get(models.AgentCredential, agent.agent_id)
    if enrolled and credential is None:
        issued_token = secrets.token_urlsafe(32)
        database.add(models.AgentCredential(
            agent_id=agent.agent_id,
            token_hash=hashlib.sha256(issued_token.encode("utf-8")).hexdigest(),
        ))
    elif enrolled and credential is not None:
        raise HTTPException(status_code=409, detail="Agent already enrolled. Use its saved credential or rotate it as administrator.")
    database.commit()
    response = {"status": "registered", "agent_id": agent.agent_id}
    if issued_token:
        response["agent_token"] = issued_token
    return response


@app.post("/api/v1/agents/{agent_id}/credential/rotate", dependencies=[Depends(authenticate_admin)])
def rotate_agent_credential(agent_id: str, database: Session = Depends(get_database)) -> dict[str, str]:
    require_agent(agent_id, database)
    issued_token = secrets.token_urlsafe(32)
    credential = database.get(models.AgentCredential, agent_id)
    token_hash = hashlib.sha256(issued_token.encode("utf-8")).hexdigest()
    if credential is None:
        credential = models.AgentCredential(agent_id=agent_id, token_hash=token_hash)
        database.add(credential)
    else:
        credential.token_hash = token_hash
        credential.created_at = datetime.now(timezone.utc)
    database.commit()
    return {"agent_id": agent_id, "agent_token": issued_token}


@app.get("/api/v1/agents", dependencies=[Depends(authenticate_user)])
def get_agents(database: Session = Depends(get_database)) -> list[dict[str, Any]]:
    agents = database.scalars(select(models.Agent).order_by(models.Agent.hostname)).all()
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
            "vms": [{"uuid": vm.uuid, "name": vm.name, "state": vm.state} for vm in vms],
        })
    return result


@app.put("/api/v1/agents/{agent_id}/vms")
def update_virtual_machines(
    agent_id: str,
    inventory: VMInventory,
    authenticated_agent_id: str = Depends(authenticate_agent),
    database: Session = Depends(get_database),
) -> dict[str, str]:
    if authenticated_agent_id != agent_id:
        raise HTTPException(status_code=403, detail="Agent credentials cannot access another agent.")
    agent = require_agent(agent_id, database)
    now = datetime.now(timezone.utc)
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
        vm = by_uuid.get(vm_uuid)
        if vm is None:
            vm = models.VirtualMachine(agent_id=agent_id, uuid=vm_uuid, name=name, state=state)
            database.add(vm)
        else:
            vm.name = name
            vm.state = state
            vm.is_present = True

    agent.last_seen = now
    database.commit()
    return {"status": "updated"}


@app.post("/api/v1/agents/{agent_id}/commands/next")
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
    now = datetime.now(timezone.utc)
    agent = database.get(models.Agent, agent_id)
    agent.last_seen = now
    if command is None:
        database.commit()
        return None

    command.status = "running"
    command.started_at = now
    vm = database.get(models.VirtualMachine, command.vm_id)
    database.commit()
    return {
        "id": command.id,
        "agent_id": command.agent_id,
        "vm_uuid": vm.uuid,
        "action": command.action,
        "status": command.status,
        "created_at": command.created_at.isoformat(),
        "started_at": command.started_at.isoformat(),
    }


@app.post("/api/v1/commands", dependencies=[Depends(authenticate_user)])
def create_command(request: CommandCreation, database: Session = Depends(get_database)) -> dict[str, Any]:
    require_agent(request.agent_id, database)
    vm = database.scalar(
        select(models.VirtualMachine).where(
            models.VirtualMachine.agent_id == request.agent_id,
            models.VirtualMachine.uuid == request.vm_uuid,
            models.VirtualMachine.is_present.is_(True),
        )
    )
    if vm is None:
        raise HTTPException(status_code=404, detail="Virtual machine not found for this agent.")

    command = models.Command(
        id=str(uuid.uuid4()),
        agent_id=request.agent_id,
        vm_id=vm.id,
        action=request.action,
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


@app.get("/api/v1/commands", dependencies=[Depends(authenticate_user)])
def get_all_commands(
    agent_id: str | None = Query(default=None),
    vm_uuid: str | None = Query(default=None),
    database: Session = Depends(get_database),
) -> list[dict[str, Any]]:
    statement = select(models.Command, models.VirtualMachine.uuid).join(
        models.VirtualMachine, models.Command.vm_id == models.VirtualMachine.id
    )
    if agent_id:
        statement = statement.where(models.Command.agent_id == agent_id)
    if vm_uuid:
        statement = statement.where(models.VirtualMachine.uuid == vm_uuid)
    rows = database.execute(statement.order_by(models.Command.created_at.desc())).all()
    return [command_as_dict(command, machine_uuid) for command, machine_uuid in rows]


@app.get("/api/v1/commands/{command_id}", dependencies=[Depends(authenticate_user)])
def get_command(command_id: str, database: Session = Depends(get_database)) -> dict[str, Any]:
    command = database.get(models.Command, command_id)
    if command is None:
        raise HTTPException(status_code=404, detail="Command not found.")
    vm = database.get(models.VirtualMachine, command.vm_id)
    return command_as_dict(command, vm.uuid)


@app.post("/api/v1/commands/{command_id}/result")
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
