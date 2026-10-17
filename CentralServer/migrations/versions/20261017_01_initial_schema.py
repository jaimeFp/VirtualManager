"""Create missing tables and upgrade early development schemas.

Revision ID: 20261017_01
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

from src.database import Base
from src import models  # noqa: F401


revision = "20261017_01"
down_revision = None
branch_labels = None
depends_on = None


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    inspector = inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return
    existing = {item["name"] for item in inspector.get_columns(table_name)}
    if column.name not in existing:
        op.add_column(table_name, column)


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)

    _add_column_if_missing(
        "web_users", sa.Column("role", sa.String(20), nullable=False, server_default="observer")
    )
    _add_column_if_missing(
        "web_users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true())
    )
    _add_column_if_missing(
        "virtual_machines", sa.Column("is_present", sa.Boolean(), nullable=False, server_default=sa.true())
    )
    _add_column_if_missing("virtual_machines", sa.Column("memory_mb", sa.Integer(), nullable=True))
    _add_column_if_missing("virtual_machines", sa.Column("cpu_count", sa.Integer(), nullable=True))
    _add_column_if_missing("virtual_machines", sa.Column("network_adapters", sa.Text(), nullable=True))
    _add_column_if_missing("commands", sa.Column("payload", sa.Text(), nullable=True))


def downgrade() -> None:
    # This baseline adopts databases with pre-existing user data; it is intentionally non-destructive.
    pass
