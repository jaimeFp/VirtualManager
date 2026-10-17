# Pruebas

Instala las dependencias de desarrollo y ejecuta la suite desde la raíz del repositorio:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Las pruebas usan una base SQLite temporal y no leen ni modifican `dev.env` ni la base de datos de desarrollo. GitHub Actions ejecuta la misma suite en cada `push` y `pull request`.
