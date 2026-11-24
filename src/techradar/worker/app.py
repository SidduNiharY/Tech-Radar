"""Procrastinate application setup for background worker."""

from procrastinate import App, PsycopgConnector

from techradar.settings import Settings, get_settings, read_secret

try:
    settings = get_settings()
except Exception:
    settings = Settings(telegram_owner_chat_id=1)

try:
    password = read_secret("tr_app_password", settings.secrets_dir)
except Exception:
    password = ""

# psycopg_pool.AsyncConnectionPool takes connection settings only inside `kwargs`
# (the libpq names, so `dbname`, not `database`); passed loose they raise TypeError.
connector = PsycopgConnector(
    kwargs={
        "host": settings.db_host,
        "port": settings.db_port,
        "dbname": settings.db_name,
        "user": "tr_app",
        "password": password,
    }
)

app = App(connector=connector)
