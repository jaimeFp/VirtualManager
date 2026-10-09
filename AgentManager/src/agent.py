import logging
import os
import platform
import socket
import time

from pathlib import Path

from commands import execute_command
from config import get_agent_id
from logging_config import configure_logging
from server_client import ServerClient
from virtualbox import (
    get_virtual_machine_state,
    list_virtual_machines,
)


SERVER_URL = "https://192.168.56.101:8443"
AGENT_VERSION = "0.1.0"
POLL_INTERVAL = 5

AGENT_TOKEN = os.environ.get("VIRTUALMANAGER_AGENT_TOKEN")

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CA_CERTIFICATE = (
    PROJECT_ROOT
    / "certs"
    / "server.crt"
)


if not AGENT_TOKEN:
    raise RuntimeError(
        "VIRTUALMANAGER_AGENT_TOKEN environment variable is not set."
    )


logger = logging.getLogger(__name__)


def get_virtual_machine_inventory() -> list[dict[str, str]]:
    """!
    @brief Get the current virtual machine inventory.
    @return List of registered virtual machines and their current states.
    """
    machines = list_virtual_machines()

    for machine in machines:
        machine["state"] = get_virtual_machine_state(
            machine["uuid"]
        )

    return machines


def main() -> None:
    """!
    @brief Run the VirtualManager agent.
    """
    configure_logging()

    agent_id = get_agent_id()

    client = ServerClient(
        SERVER_URL,
        AGENT_TOKEN,
        str(CA_CERTIFICATE),
    )

    logger.info(
        "Starting VirtualManager Agent version %s",
        AGENT_VERSION,
    )

    logger.info(
        "Agent ID: %s",
        agent_id,
    )

    logger.info(
        "Central server: %s",
        SERVER_URL,
    )

    try:
        client.register_agent(
            agent_id=agent_id,
            hostname=socket.gethostname(),
            platform=platform.system().lower(),
            version=AGENT_VERSION,
        )

        logger.info(
            "Agent registered successfully."
        )

    except Exception:
        logger.exception(
            "Unable to register agent."
        )
        return

    while True:
        try:
            machines = get_virtual_machine_inventory()

            logger.debug(
                "Detected %d virtual machines.",
                len(machines),
            )

            client.update_virtual_machines(
                agent_id,
                machines,
            )

            command = client.get_next_command(
                agent_id,
            )

            if command is not None:
                command_id = command["id"]

                logger.info(
                    "Command received: id=%s action=%s vm_uuid=%s",
                    command_id,
                    command["action"],
                    command["vm_uuid"],
                )

                logger.info(
                    "Executing command %s.",
                    command_id,
                )

                try:
                    execute_command(
                        command,
                    )

                    client.report_command_result(
                        command_id,
                        "success",
                    )

                    logger.info(
                        "Command %s completed successfully.",
                        command_id,
                    )

                except Exception as error:
                    logger.exception(
                        "Command %s failed.",
                        command_id,
                    )

                    try:
                        client.report_command_result(
                            command_id,
                            "failed",
                            str(error),
                        )

                    except Exception:
                        logger.exception(
                            "Unable to report result for command %s.",
                            command_id,
                        )

        except Exception:
            logger.exception(
                "Agent communication cycle failed."
            )

        time.sleep(
            POLL_INTERVAL,
        )


if __name__ == "__main__":
    main()
