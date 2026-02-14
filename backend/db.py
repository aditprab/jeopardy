import psycopg2
from psycopg2 import pool

_pool: pool.SimpleConnectionPool | None = None


def init_pool():
    global _pool
    _pool = pool.SimpleConnectionPool(
        minconn=1,
        maxconn=10,
        dbname="jeopardy",
        user="jeopardy",
        password="jeopardy",
        host="localhost",
        port=5433,
    )


def get_conn():
    return _pool.getconn()


def put_conn(conn):
    _pool.putconn(conn)


def close_pool():
    if _pool:
        _pool.closeall()
