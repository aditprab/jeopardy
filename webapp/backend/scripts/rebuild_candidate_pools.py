#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from datetime import date, datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import psycopg2
from psycopg2.extras import execute_values

SINGLE_VALUES = [200, 400, 600, 800, 1000]
DOUBLE_VALUES = [400, 800, 1200, 1600, 2000]


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _with_sslmode_if_needed(db_url: str) -> str:
    sslmode = os.getenv("DB_SSLMODE")
    if not sslmode:
        return db_url
    parsed = urlparse(db_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("sslmode", sslmode)
    return urlunparse(parsed._replace(query=urlencode(query)))


def _connect(database_url: str | None):
    if database_url:
        return psycopg2.connect(_with_sslmode_if_needed(database_url))
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5433")),
        dbname=os.getenv("DB_NAME", "jeopardy"),
        user=os.getenv("DB_USER", "jeopardy"),
        password=os.getenv("DB_PASSWORD", "jeopardy"),
        sslmode=os.getenv("DB_SSLMODE", "disable"),
    )


def _ensure_pool_tables(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS candidate_jd_pairs (
            ordinal INT PRIMARY KEY,
            single_category_id INT NOT NULL REFERENCES categories(id),
            double_category_id INT NOT NULL REFERENCES categories(id),
            single_game_id INT NOT NULL REFERENCES games(id),
            double_game_id INT NOT NULL REFERENCES games(id),
            single_air_date DATE NOT NULL,
            double_air_date DATE NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS candidate_finals (
            ordinal INT PRIMARY KEY,
            final_clue_id INT NOT NULL REFERENCES clues(id),
            game_id INT NOT NULL REFERENCES games(id),
            air_date DATE NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def _load_single_stream(cur, start_date: date) -> list[tuple[int, int, date]]:
    cur.execute(
        """
        SELECT
            c.game_id,
            c.category_id,
            g.air_date
        FROM clues c
        JOIN games g ON g.id = c.game_id
        WHERE c.round = 1
          AND g.air_date >= %s
        GROUP BY c.game_id, c.category_id, g.air_date
        HAVING COUNT(*) = 5
           AND ARRAY_AGG(c.clue_value ORDER BY c.clue_value) = %s::INT[]
        ORDER BY g.air_date ASC, c.game_id ASC, c.category_id ASC
        """,
        (start_date, SINGLE_VALUES),
    )
    return [(int(gid), int(cid), air_date) for gid, cid, air_date in cur.fetchall()]


def _load_double_stream(cur, start_date: date) -> list[tuple[int, int, date]]:
    cur.execute(
        """
        SELECT
            c.game_id,
            c.category_id,
            g.air_date
        FROM clues c
        JOIN games g ON g.id = c.game_id
        WHERE c.round = 2
          AND g.air_date >= %s
        GROUP BY c.game_id, c.category_id, g.air_date
        HAVING COUNT(*) = 5
           AND ARRAY_AGG(c.clue_value ORDER BY c.clue_value) = %s::INT[]
        ORDER BY g.air_date ASC, c.game_id ASC, c.category_id ASC
        """,
        (start_date, DOUBLE_VALUES),
    )
    return [(int(gid), int(cid), air_date) for gid, cid, air_date in cur.fetchall()]


def _load_final_stream(cur, start_date: date) -> list[tuple[int, int, date]]:
    cur.execute(
        """
        SELECT
            g.id AS game_id,
            MIN(c.id) AS final_clue_id,
            g.air_date
        FROM games g
        JOIN clues c ON c.game_id = g.id
        WHERE c.round = 3
          AND g.air_date >= %s
        GROUP BY g.id, g.air_date
        ORDER BY g.air_date ASC, g.id ASC
        """,
        (start_date,),
    )
    return [(int(gid), int(fid), air_date) for gid, fid, air_date in cur.fetchall()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild candidate pools for lazy daily challenge selection.")
    parser.add_argument(
        "--database-url",
        help="Optional Postgres URL override. If omitted, local DB_* env vars are used.",
    )
    parser.add_argument(
        "--start-date",
        default="2005-01-01",
        help="Earliest game air_date included in candidate pools (default: 2005-01-01).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and print pool stats without writing.",
    )
    args = parser.parse_args()

    start_date = _parse_date(args.start_date)
    conn = _connect(args.database_url)
    try:
        with conn.cursor() as cur:
            _ensure_pool_tables(cur)
            singles = _load_single_stream(cur, start_date)
            doubles = _load_double_stream(cur, start_date)
            finals = _load_final_stream(cur, start_date)

            jd_len = min(len(singles), len(doubles))
            jd_rows = [
                (
                    i,
                    singles[i][1],
                    doubles[i][1],
                    singles[i][0],
                    doubles[i][0],
                    singles[i][2],
                    doubles[i][2],
                )
                for i in range(jd_len)
            ]
            final_rows = [(i, finals[i][1], finals[i][0], finals[i][2]) for i in range(len(finals))]

            print(
                f"single_stream={len(singles)} "
                f"double_stream={len(doubles)} "
                f"final_stream={len(finals)} "
                f"jd_pairs={len(jd_rows)}"
            )
            if jd_rows:
                first = jd_rows[0]
                last = jd_rows[-1]
                print(
                    "jd_preview_first="
                    f"ordinal:{first[0]} single_cat:{first[1]} double_cat:{first[2]} "
                    f"single_game:{first[3]} double_game:{first[4]}"
                )
                print(
                    "jd_preview_last="
                    f"ordinal:{last[0]} single_cat:{last[1]} double_cat:{last[2]} "
                    f"single_game:{last[3]} double_game:{last[4]}"
                )
            if final_rows:
                first_f = final_rows[0]
                last_f = final_rows[-1]
                print(
                    "final_preview_first="
                    f"ordinal:{first_f[0]} final_clue:{first_f[1]} game:{first_f[2]}"
                )
                print(
                    "final_preview_last="
                    f"ordinal:{last_f[0]} final_clue:{last_f[1]} game:{last_f[2]}"
                )

            if args.dry_run:
                conn.rollback()
                return

            cur.execute("TRUNCATE TABLE candidate_jd_pairs")
            cur.execute("TRUNCATE TABLE candidate_finals")

            if jd_rows:
                execute_values(
                    cur,
                    """
                    INSERT INTO candidate_jd_pairs (
                        ordinal,
                        single_category_id,
                        double_category_id,
                        single_game_id,
                        double_game_id,
                        single_air_date,
                        double_air_date
                    )
                    VALUES %s
                    """,
                    jd_rows,
                    template="(%s, %s, %s, %s, %s, %s, %s)",
                    page_size=1000,
                )
            if final_rows:
                execute_values(
                    cur,
                    """
                    INSERT INTO candidate_finals (
                        ordinal,
                        final_clue_id,
                        game_id,
                        air_date
                    )
                    VALUES %s
                    """,
                    final_rows,
                    template="(%s, %s, %s, %s)",
                    page_size=1000,
                )
        conn.commit()
        print("candidate_pool_rebuild=ok")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
