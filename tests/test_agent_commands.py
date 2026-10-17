import pytest

import virtualbox
import commands


def test_inventory_details_parses_resources_and_network_interfaces(monkeypatch):
    monkeypatch.setattr(virtualbox, "get_virtual_machine_info", lambda _uuid: {
        "memory": "4096",
        "cpus": "4",
        "nic1": "nat",
        "cableconnected1": "on",
        "nic2": "bridged",
        "bridgeadapter2": "Wi-Fi",
        "cableconnected2": "off",
        "nic3": "null",
        "nic4": "none",
    })

    details = virtualbox.get_virtual_machine_inventory_details("vm-id")

    assert details["memory_mb"] == 4096
    assert details["cpu_count"] == 4
    adapters = details["network_adapters"]
    assert len(adapters) == 8
    assert adapters[0] == {
        "slot": 1, "enabled": True, "mode": "nat", "adapter": "", "cable_connected": True,
    }
    assert adapters[1] == {
        "slot": 2, "enabled": True, "mode": "bridged", "adapter": "Wi-Fi", "cable_connected": False,
    }
    assert adapters[2]["enabled"] is True
    assert adapters[2]["mode"] == "null"
    assert adapters[3]["enabled"] is False


def test_inventory_details_defaults_unreported_interfaces_to_disabled(monkeypatch):
    monkeypatch.setattr(virtualbox, "get_virtual_machine_info", lambda _uuid: {
        "memory": "1024",
        "cpus": "1",
    })

    details = virtualbox.get_virtual_machine_inventory_details("vm-id")

    assert details["network_adapters"] == [
        {
            "slot": slot,
            "enabled": False,
            "mode": "none",
            "adapter": "",
            "cable_connected": True,
        }
        for slot in range(1, 9)
    ]


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
