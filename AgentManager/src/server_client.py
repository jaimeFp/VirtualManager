from typing import Any

import httpx



class ServerClient:
    """!
    @brief Client used by the agent to communicate with the central server.
    """

    def __init__(self,server_url: str,token:str,ca_certificate: str,timeout: float = 10.0,) -> None:
        """!
        @brief Initialize the central server client.
        @param server_url Base URL of the central server.
        @param timeout HTTP request timeout in seconds.
        """
        self.client = httpx.Client(
            base_url=server_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            verify=ca_certificate,
            timeout=timeout,
        )
        

    def register_agent(self,agent_id: str,hostname: str,platform: str,version: str) -> dict[str, Any]:
        """!
        @brief Register the agent with the central server.
        @return Server response.
        """
        response = self.client.post(
            f"/api/v1/agents/register",
            json={
                "agent_id": agent_id,
                "hostname": hostname,
                "platform": platform,
                "version": version,
            },
        )

        response.raise_for_status()

        return response.json()

    def update_virtual_machines(self,agent_id: str,machines: list[dict[str, Any]]) -> dict[str, Any]:
        """!
        @brief Send the current virtual machine inventory to the server.
        @return Server response.
        """
        response = self.client.put(
            f"/api/v1/agents/{agent_id}/vms",
            json={"vms": machines},
        )

        response.raise_for_status()

        return response.json()

    def get_next_command(
        self,
        agent_id: str,
    ) -> dict[str, Any] | None:
        """!
        @brief Get and claim the next pending command for the agent.
        @param agent_id Unique identifier of the agent.
        @return Claimed command or None if no command is pending.
        """
        response = self.client.post(
            f"/api/v1/agents/{agent_id}/commands/next"
        )
    
        response.raise_for_status()
    
        return response.json()

    def report_command_result(self,command_id: str,status: str,error: str | None = None,) -> None:
        """!
        @brief Report the result of a command execution.
        @param command_id Unique identifier of the command.
        @param status Command execution status.
        @param error Optional error description.
        """
        response = self.client.post(
            f"/api/v1/commands/{command_id}/result",
            json={
                "status": status,
                "error": error,
            },
        )

        response.raise_for_status()