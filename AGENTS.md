# Working in VirtualManager

- `CentralServer` is the web/API service. `AgentManager` runs on each host and controls that host's VirtualBox installation.
- Keep component dependencies and runtime code inside their component. Put shared project tests in `tests/` and project documentation in `documentation/`.
- When adding, removing, or changing a test function, update `documentation/TESTING.md` in the same change with its name and what it verifies.
- Run `python -m pytest -q` and `python -m compileall -q AgentManager/src CentralServer/src tests` before committing.
- VirtualBox calls in tests must be mocked; tests must not control a real VM.
- Never commit or print `dev.env`, agent credentials, database passwords, or private TLS keys.
- Keep the public `CentralServer/src/main.py` ASGI import available for existing run commands.
