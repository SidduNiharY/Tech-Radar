"""The procrastinate connectors must build a pool psycopg_pool accepts.

AsyncConnectionPool(**kwargs) has no `host`/`database` parameters: loose connection
settings raised TypeError when the pool opened, so neither the worker nor the bot could
queue a job. Settings go in `kwargs=` with libpq names (`dbname`).
"""

import inspect

import psycopg_pool

from techradar.worker.app import connector

POOL_PARAMS = set(inspect.signature(psycopg_pool.AsyncConnectionPool.__init__).parameters)


def test_worker_connector_passes_only_pool_parameters():
    pool_args = connector._pool_args
    assert set(pool_args) <= POOL_PARAMS
    assert pool_args["kwargs"]["dbname"]
    assert "database" not in pool_args["kwargs"]


def test_bot_builds_the_connector_the_same_way():
    import techradar.bot.main as bot_main

    src = inspect.getsource(bot_main.post_init)
    assert '"dbname": settings.db_name' in src and "database=" not in src
