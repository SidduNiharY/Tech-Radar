"""Procrastinate application setup for background worker."""

from procrastinate import App, PsycopgConnector

from techradar.settings import settings

connector = PsycopgConnector(
    host=settings.db_host,
    port=settings.db_port,
    user=settings.postgres_user,
    password=settings.postgres_password.get_secret_value(),
    database=settings.postgres_db,
)

app = App(connector=connector)
