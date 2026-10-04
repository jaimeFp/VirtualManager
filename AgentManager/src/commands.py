from typing import Any

from virtualbox import (
    pause_virtual_machine,
    poweroff_virtual_machine,
    resume_virtual_machine,
    shutdown_virtual_machine,
    start_virtual_machine,
)


def execute_command(command: dict[str, Any]) -> None:
    """!
    @brief Execute a virtual machine command.
    @param command Command received from the central server.
    @exception ValueError If the requested action is not supported.
    """
    action = command["action"]
    uuid = command["vm_uuid"]

    if action == "start":
        start_virtual_machine(uuid)

    elif action == "pause":
        pause_virtual_machine(uuid)

    elif action == "resume":
        resume_virtual_machine(uuid)

    elif action == "shutdown":
        shutdown_virtual_machine(uuid)

    elif action == "poweroff":
        poweroff_virtual_machine(uuid)

    else:
        raise ValueError(
            f"Unsupported virtual machine action: {action!r}"
        )