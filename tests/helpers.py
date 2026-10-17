import hashlib
import uuid
from datetime import datetime, timezone

from src import models

TEST_PASSWORD = "TestPassword123!"


def create_agent(database, name="agent-one", state="poweroff"):
    agent_id = str(uuid.uuid4())
    vm_uuid = str(uuid.uuid4())
    agent = models.Agent(
        id=agent_id,
        hostname=name,
        platform="windows",
        version="test",
        last_seen=datetime.now(timezone.utc),
    )
    vm = models.VirtualMachine(
        id=str(uuid.uuid4()),
        agent_id=agent_id,
        uuid=vm_uuid,
        name="Test VM",
        state=state,
        is_present=True,
    )
    token = f"agent-token-{agent_id}"
    database.add_all([
        agent,
        vm,
        models.AgentCredential(
            agent_id=agent_id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
        ),
    ])
    database.commit()
    return {"agent_id": agent_id, "vm_uuid": vm_uuid, "token": token}


def create_user(database, username, role, agent_ids=(), active=True):
    user = models.WebUser(
        id=str(uuid.uuid4()),
        username=username,
        password_hash="",
        role=role,
        is_active=active,
    )
    database.add(user)
    database.flush()
    database.add_all([
        models.WebUserAgentAccess(user_id=user.id, agent_id=agent_id)
        for agent_id in agent_ids
    ])
    database.commit()
    return user
