# Pruebas

Instala las dependencias de desarrollo y ejecuta la suite desde la raíz del repositorio:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Las pruebas usan una base SQLite temporal y no leen ni modifican `dev.env` ni la base de datos de desarrollo. GitHub Actions ejecuta la misma suite en cada `push` y `pull request`.

## Cobertura actual

Cada función de test se documenta aquí con su objetivo. Al añadir, eliminar o cambiar un test, actualiza esta lista en el mismo cambio.

### `tests/test_auth_and_permissions.py`

- `test_login_session_lifecycle`: comprueba que el acceso requiere iniciar sesión, que las credenciales incorrectas se rechazan, que la cookie de sesión lleva los atributos de seguridad y que cerrar sesión invalida la sesión.
- `test_observer_can_only_read_and_only_assigned_agents`: comprueba que un observador solo ve sus agentes asignados y que no puede enviar órdenes ni consultar agentes fuera de su ámbito.
- `test_operator_can_command_assigned_agent_only`: comprueba que un operador puede enviar una orden a una VM de un agente asignado y recibe denegación para agentes no asignados.

### `tests/test_agent_api.py`

- `test_agent_inventory_is_scoped_and_persists_resource_data`: comprueba que la credencial de un agente no puede actualizar el inventario de otro, y que el servidor guarda y devuelve RAM, CPU e interfaces de red.
- `test_configuration_command_is_validated_and_delivered_to_agent`: comprueba que el servidor rechaza configuraciones inválidas y cambios con la VM encendida, y que entrega al agente la configuración válida solicitada.
- `test_invalid_agent_credential_is_rejected`: comprueba que una credencial de agente inválida no permite actualizar el inventario.

### `tests/test_agent_commands.py`

- `test_inventory_details_parses_resources_and_network_interfaces`: comprueba que el agente lee RAM, CPU y modos de red desde la salida de VirtualBox, incluyendo el nombre de adaptador y el estado del cable.
- `test_inventory_details_defaults_unreported_interfaces_to_disabled`: comprueba que el inventario siempre incluye las ocho interfaces y marca como desactivadas las que VirtualBox no informa.
- `test_configure_virtual_machine_builds_expected_vboxmanage_arguments`: comprueba que la configuración genera los argumentos correctos de `VBoxManage` para RAM, CPU e interfaces de red.
- `test_configure_virtual_machine_requires_powered_off_state`: comprueba que el agente no modifica recursos si la VM no está apagada.
- `test_agent_dispatches_configuration_payload`: comprueba que el despachador entrega al configurador del agente la VM y el contenido de la orden recibida.
