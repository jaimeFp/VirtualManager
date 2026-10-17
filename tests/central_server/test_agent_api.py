from src import main
from src.database import SessionLocal
from tests.helpers import create_agent


def test_agent_inventory_is_scoped_and_persists_resource_data(admin_client):
    with SessionLocal() as database:
        agent = create_agent(database)
    headers = {"Authorization": f"Bearer {agent['token']}"}
    inventory = {"vms": [{
        "uuid": agent["vm_uuid"],
        "name": "Test VM",
        "state": "poweroff",
        "memory_mb": 4096,
        "cpu_count": 4,
        "network_adapters": [{"slot": 1, "mode": "nat", "enabled": True}],
    }]}
    denied = admin_client.put(f"/api/v1/agents/{'00000000-0000-0000-0000-000000000099'}/vms", headers=headers, json=inventory)
    assert denied.status_code == 403
    updated = admin_client.put(f"/api/v1/agents/{agent['agent_id']}/vms", headers=headers, json=inventory)
    assert updated.status_code == 200

    visible = admin_client.get("/api/v1/agents").json()
    vm = visible[0]["vms"][0]
    assert vm["memory_mb"] == 4096
    assert vm["cpu_count"] == 4
    assert vm["network_adapters"][0]["mode"] == "nat"


def test_configuration_command_is_validated_and_delivered_to_agent(admin_client):
    with SessionLocal() as database:
        agent = create_agent(database, "powered-off")
        running = create_agent(database, "running", state="running")
    adapters = [{"slot": slot, "enabled": slot == 1, "mode": "nat", "adapter": "", "cable_connected": True} for slot in range(1, 9)]
    payload = {"memory_mb": 4096, "cpu_count": 4, "network_adapters": adapters}
    url = "/api/v1/commands"

    bad_payload = admin_client.post(url, json={
        "agent_id": agent["agent_id"], "vm_uuid": agent["vm_uuid"], "action": "configure",
        "payload": {**payload, "cpu_count": 0},
    })
    assert bad_payload.status_code == 422
    running_vm = admin_client.post(url, json={
        "agent_id": running["agent_id"], "vm_uuid": running["vm_uuid"], "action": "configure", "payload": payload,
    })
    assert running_vm.status_code == 409

    created = admin_client.post(url, json={
        "agent_id": agent["agent_id"], "vm_uuid": agent["vm_uuid"], "action": "configure", "payload": payload,
    })
    assert created.status_code == 200
    agent_response = admin_client.post(
        f"/api/v1/agents/{agent['agent_id']}/commands/next",
        headers={"Authorization": f"Bearer {agent['token']}"},
    )
    assert agent_response.status_code == 200
    assert agent_response.json()["payload"] == payload


def test_invalid_agent_credential_is_rejected(client):
    response = client.put(
        "/api/v1/agents/00000000-0000-0000-0000-000000000001/vms",
        headers={"Authorization": "Bearer invalid"},
        json={"vms": []},
    )
    assert response.status_code == 401
