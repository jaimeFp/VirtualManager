"""Compatibility ASGI entry point. The application is assembled in ``src.app``."""

from sqlalchemy import select

from . import models
from .app import app
from .database import Base, engine, get_database
from .security import hash_password

__all__ = ["app", "Base", "engine", "get_database", "hash_password", "models", "select"]
