"""Database engine configuration and role-specific connection URLs."""

from typing import Literal

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from techradar.settings import Settings, get_settings, read_secret

DbRole = Literal["migrator", "app", "ro"]


def database_url(role: DbRole, s: Settings | None = None) -> str:
    """Return database connection URL for the given role."""
    if role not in ("migrator", "app", "ro"):
        raise ValueError(f"Invalid db role: {role!r}. Expected 'migrator', 'app', or 'ro'")
    if s is None:
        s = get_settings()
    secret = read_secret(f"tr_{role}_password", s.secrets_dir)
    return f"postgresql+psycopg://tr_{role}:{secret}@{s.db_host}:{s.db_port}/{s.db_name}"


def make_engine(role: DbRole, s: Settings | None = None) -> AsyncEngine:
    """Create an asynchronous engine for the given database role."""
    return create_async_engine(database_url(role, s), pool_pre_ping=True)


def make_session_factory(
    role: DbRole, s: Settings | None = None
) -> async_sessionmaker[AsyncSession]:
    """Create an asynchronous sessionmaker for the given database role."""
    engine = make_engine(role, s)
    return async_sessionmaker(engine, expire_on_commit=False)
