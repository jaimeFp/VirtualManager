# Authentication model

VirtualManager uses separate credentials for the browser, agent enrollment, and each installed agent.

- The browser signs in with `VIRTUALMANAGER_WEB_USERNAME` and `VIRTUALMANAGER_WEB_PASSWORD`. The server stores a salted PBKDF2 password hash and issues an eight-hour, HttpOnly, Secure, SameSite=Strict session cookie. The username and password variables bootstrap the first account only; changing them after an account exists does not reset its password.
- Web accounts have one of three roles: `admin` manages users and rotates agent credentials; `operator` can view inventory and send VM commands; `observer` has read-only access. The server enforces these permissions on every protected API route.
- A new agent uses `VIRTUALMANAGER_ENROLLMENT_TOKEN` once at `/api/v1/agents/register`. The server returns a random agent credential once; the agent saves it in its local `config/agent.json` and uses it for later requests.
- Agent credentials are stored as SHA-256 hashes in the server database and are scoped to one agent. An agent cannot read another agent's inventory or claim or report its commands.
- An administrator can revoke an agent credential from the dashboard API. The replacement credential is returned once; update the agent's saved `agent_token` in `AgentManager/config/agent.json` before restarting it.

Set the enrollment and web account variables in `CentralServer/dev.env`. Add `VIRTUALMANAGER_ENROLLMENT_TOKEN` to an agent's `AgentManager/dev.env` only while enrolling it. Once the agent has saved its individual credential, remove the enrollment value from that machine and rotate the server's enrollment value. Existing agents continue using their individual credentials; give the new enrollment value only to the next machine being installed.

Set the web username and password in the ignored `CentralServer/dev.env` before the first server start. The initial password must contain at least 12 characters. Do not commit environment files or the agent configuration file.
