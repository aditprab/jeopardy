import os
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import psycopg2
from psycopg2 import pool

_pool: pool.SimpleConnectionPool | None = None


def _with_sslmode_if_needed(db_url: str) -> str:
    sslmode = os.getenv("DB_SSLMODE")
    if not sslmode:
        return db_url
    parsed = urlparse(db_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("sslmode", sslmode)
    return urlunparse(parsed._replace(query=urlencode(query)))


def _pool_kwargs() -> dict:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return {"dsn": _with_sslmode_if_needed(database_url)}

    return {
        "dbname": os.getenv("DB_NAME", "jeopardy"),
        "user": os.getenv("DB_USER", "jeopardy"),
        "password": os.getenv("DB_PASSWORD", "jeopardy"),
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5433")),
        "sslmode": os.getenv("DB_SSLMODE", "disable"),
    }


def init_pool():
    global _pool
    _pool = pool.SimpleConnectionPool(
        minconn=1,
        maxconn=10,
        **_pool_kwargs(),
    )


def get_conn():
    return _pool.getconn()


def put_conn(conn):
    _pool.putconn(conn)


def close_pool():
    if _pool:
        _pool.closeall()
