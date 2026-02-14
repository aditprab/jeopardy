"""Run schema.sql against the Postgres instance."""

import psycopg2
import sys
from pathlib import Path

DB_CONFIG = dict(
    host="localhost",
    port=5433,
    dbname="jeopardy",
    user="jeopardy",
    password="jeopardy",
)


def main():
    schema_sql = Path(__file__).parent.parent / "schema.sql"
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(schema_sql.read_text())
    cur.close()
    conn.close()
    print("Schema created successfully.")


if __name__ == "__main__":
    main()
