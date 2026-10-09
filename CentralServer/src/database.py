import os

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


DATABASE_URL = os.environ.get(
    "VIRTUALMANAGER_DATABASE_URL"
)

if not DATABASE_URL:
    raise RuntimeError(
        "VIRTUALMANAGER_DATABASE_URL environment variable is not set."
    )


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """!
    @brief Base class for SQLAlchemy database models.
    """

    pass


def get_database() -> Generator[Session, None, None]:
    """!
    @brief Provide a database session.
    @return SQLAlchemy database session.
    """
    database = SessionLocal()

    try:
        yield database

    finally:
        database.close()