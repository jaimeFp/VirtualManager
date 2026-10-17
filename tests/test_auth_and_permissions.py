from src import main
from src.database import SessionLocal
from tests.helpers import TEST_PASSWORD, create_agent, create_user


def test_login_session_lifecycle(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    invalid = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert invalid.status_code == 401

    response = client.post("/api/v1/auth/login", json={"username": " ADMIN ", "password": TEST_PASSWORD})
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=strict" in cookie
    assert client.get("/api/v1/auth/me").json()["role"] == "admin"
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_observer_can_only_read_and_only_assigned_agents(admin_client):
    with SessionLocal() as database:
        assigned = create_agent(database, "assigned")
        unassigned = create_agent(database, "unassigned")
        create_user(database, "observer", "observer", [assigned["agent_id"]])

    observer = admin_client.__class__(app=main.app, base_url="https://testserver")
    with SessionLocal() as database:
        user = database.scalar(main.select(main.models.WebUser).where(main.models.WebUser.username == "observer"))
        user.password_hash = main.hash_password("ObserverPassword123!")
        database.commit()
    response = observer.post("/api/v1/auth/login", json={"username": "observer", "password": "ObserverPassword123!"})
    assert response.status_code == 200
    visible = observer.get("/api/v1/agents").json()
    assert [agent["agent_id"] for agent in visible] == [assigned["agent_id"]]
    assert observer.post("/api/v1/commands", json={
        "agent_id": assigned["agent_id"], "vm_uuid": assigned["vm_uuid"], "action": "start",
    }).status_code == 403
    assert observer.get(f"/api/v1/commands?agent_id={unassigned['agent_id']}").status_code == 403


def test_operator_can_command_assigned_agent_only(admin_client):
    with SessionLocal() as database:
        assigned = create_agent(database, "assigned")
        unassigned = create_agent(database, "unassigned")
        operator = create_user(database, "operator", "operator", [assigned["agent_id"]])
        operator.password_hash = main.hash_password("OperatorPassword123!")
        database.commit()

    operator_client = admin_client.__class__(app=main.app, base_url="https://testserver")
    login = operator_client.post("/api/v1/auth/login", json={"username": "operator", "password": "OperatorPassword123!"})
    assert login.status_code == 200
    accepted = operator_client.post("/api/v1/commands", json={
        "agent_id": assigned["agent_id"], "vm_uuid": assigned["vm_uuid"], "action": "start",
    })
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "pending"
    denied = operator_client.post("/api/v1/commands", json={
        "agent_id": unassigned["agent_id"], "vm_uuid": unassigned["vm_uuid"], "action": "start",
    })
    assert denied.status_code == 403
