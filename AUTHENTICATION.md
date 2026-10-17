# Authentication model

VirtualManager uses separate credentials for the browser, agent enrollment, and each installed agent.

- The browser signs in with `VIRTUALMANAGER_WEB_USERNAME` and `VIRTUALMANAGER_WEB_PASSWORD`. The server stores a salted PBKDF2 password hash and issues an eight-hour, HttpOnly, Secure, SameSite=Strict session cookie. The username and password variables bootstrap the first account only; changing them after an account exists does not reset its password.
- The separate `VIRTUALMANAGER_ADMIN_TOKEN` remains for internal administrative API operations such as rotating an agent credential. It is not used by the web page.
- A new agent uses `VIRTUALMANAGER_ENROLLMENT_TOKEN` once at `/api/v1/agents/register`. The server returns a random agent credential once; the agent saves it in its local `config/agent.json` and uses it for later requests.
- Agent credentials are stored as SHA-256 hashes in the server database and are scoped to one agent. An agent cannot read another agent's inventory or claim or report its commands.
- To revoke an agent credential, call `POST /api/v1/agents/{agent_id}/credential/rotate` with the admin Bearer token. The response contains the replacement credential once. Update the agent's saved `agent_token` in `AgentManager/config/agent.json` before restarting it.

Set both server variables in `CentralServer/dev.env` and keep them different. Add `VIRTUALMANAGER_ENROLLMENT_TOKEN` to an agent's `AgentManager/dev.env` only while enrolling it. Once the agent has saved its individual credential, remove the enrollment value from that machine and rotate the server's enrollment value. Existing agents continue using their individual credentials; give the new enrollment value only to the next machine being installed.

Set the web username and password in the ignored `CentralServer/dev.env` before the first server start. The initial password must contain at least 12 characters. Keep the admin and enrollment values different; do not commit either environment file or the agent configuration file.
