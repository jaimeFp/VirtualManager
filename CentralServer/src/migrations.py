from pathlib import Path

from alembic import command
from alembic.config import Config


def upgrade_database() -> None:
    """Apply all database revisions using the configured service URL."""
    server_root = Path(__file__).resolve().parents[1]
    config = Config(str(server_root / "alembic.ini"))
    config.set_main_option("script_location", str(server_root / "migrations"))
    command.upgrade(config, "head")
