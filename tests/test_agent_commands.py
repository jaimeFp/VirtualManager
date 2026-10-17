import pytest

import virtualbox
import commands


def test_configure_virtual_machine_builds_expected_vboxmanage_arguments(monkeypatch):
    calls = []
    monkeypatch.setattr(virtualbox, "get_virtual_machine_state", lambda _uuid: "poweroff")
    monkeypatch.setattr(virtualbox, "run_vboxmanage", lambda args, timeout=30: calls.append((args, timeout)))
    adapters = [{"slot": slot, "enabled": slot == 1, "mode": "bridged", "adapter": "Wi-Fi", "cable_connected": True} for slot in range(1, 9)]

    virtualbox.configure_virtual_machine("vm-id", {
        "memory_mb": 2048, "cpu_count": 2, "network_adapters": adapters,
    })

    args, timeout = calls[0]
    assert args[:6] == ["modifyvm", "vm-id", "--memory", "2048", "--cpus", "2"]
    assert ["--nic1", "bridged", "--bridgeadapter1", "Wi-Fi"] == args[6:10]
    assert ["--nic2", "none"] == args[12:14]
    assert timeout == 60.0


def test_configure_virtual_machine_requires_powered_off_state(monkeypatch):
    monkeypatch.setattr(virtualbox, "get_virtual_machine_state", lambda _uuid: "running")
    with pytest.raises(ValueError, match="apagada"):
        virtualbox.configure_virtual_machine("vm-id", {})


def test_agent_dispatches_configuration_payload(monkeypatch):
    received = []
    monkeypatch.setattr(commands, "configure_virtual_machine", lambda uuid, payload: received.append((uuid, payload)))
    configuration = {"memory_mb": 2048, "cpu_count": 2, "network_adapters": []}

    commands.execute_command({"action": "configure", "vm_uuid": "vm-id", "payload": configuration})

    assert received == [("vm-id", configuration)]
