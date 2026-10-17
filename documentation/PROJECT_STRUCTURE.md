# Estructura del proyecto

## Componentes

- `CentralServer/src/app.py`: composición de FastAPI, ciclo de vida y montaje del frontend.
- `CentralServer/src/routers/`: endpoints agrupados por autenticación, agentes, usuarios y órdenes.
- `CentralServer/src/security.py`, `dependencies.py`, `schemas.py` y `bootstrap.py`: seguridad, autorización, validación de entrada e inicialización del usuario administrador.
- `CentralServer/migrations/`: migraciones versionadas de Alembic. El servidor aplica las pendientes al arrancar.
- `CentralServer/src/frontend/`: aplicación web estática. `assets/app.js` coordina vistas y eventos; `assets/api.js` concentra las llamadas HTTP; `assets/helpers.js` contiene etiquetas, formato y funciones de presentación compartidas.
- `AgentManager/src/virtualmanager_agent/`: paquete Python instalable del agente. Se puede ejecutar con `python -m virtualmanager_agent` desde `AgentManager`.
- `tests/central_server/` y `tests/agent/`: pruebas agrupadas por componente; `tests/conftest.py` y `tests/helpers.py` contienen configuración y utilidades compartidas.
- `documentation/`: documentación funcional y técnica del proyecto.

## Límites de dependencias

Los routers dependen de servicios compartidos y modelos; `app.py` los conecta. El agente es un paquete independiente del servidor y se comunica con él por la API HTTPS. Las pruebas del agente simulan las llamadas a VirtualBox para poder ejecutarse en CI sin instalar VirtualBox.

Mantén los archivos de documentación en `documentation/`. Al añadir o modificar pruebas, actualiza `documentation/TESTING.md` con el nombre de cada función de prueba y lo que comprueba.
