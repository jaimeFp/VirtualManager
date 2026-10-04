import json
import uuid

from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent

CONFIG_DIRECTORY = PROJECT_ROOT / "config"
CONFIG_FILE = CONFIG_DIRECTORY / "agent.json"


def load_config() -> dict[str, Any]:
    """!
    @brief Load the agent configuration from disk.
    @return Agent configuration.
    @details If the configuration file does not exist, an empty dictionary
             is returned.
    """
    if not CONFIG_FILE.exists():
        return {}

    with CONFIG_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def save_config(config: dict[str, Any]) -> None:
    """!
    @brief Save the agent configuration to disk.
    @param config Agent configuration to persist.
    """
    CONFIG_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    with CONFIG_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            config,
            file,
            indent=4,
        )


def get_agent_id() -> str:
    """!
    @brief Get the persistent agent identifier.
    @return Persistent UUID assigned to this agent.
    @details If no identifier exists, a new UUID is generated and stored.
    """
    config = load_config()

    agent_id = config.get("agent_id")

    if agent_id:
        return agent_id

    agent_id = str(uuid.uuid4())

    config["agent_id"] = agent_id
    save_config(config)

    return agent_id