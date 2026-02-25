#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

try:
    import psycopg2
except ImportError as exc:  # pragma: no cover - runtime environment dependency
    raise SystemExit(
        "Missing dependency 'psycopg2'. Install backend deps with:\n"
        "  pip install -r webapp/backend/requirements.txt"
    ) from exc

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from ..grading import grade_and_record
except ImportError:
    from grading import grade_and_record


def _with_sslmode_if_needed(db_url: str) -> str:
    sslmode = os.getenv("DB_SSLMODE")
    if not sslmode:
        return db_url
    parsed = urlparse(db_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("sslmode", sslmode)
    return urlunparse(parsed._replace(query=urlencode(query)))


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def _connect(database_url: str | None):
    db_url = database_url or os.getenv("DATABASE_URL")
    if db_url:
        return psycopg2.connect(_with_sslmode_if_needed(db_url))
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5433")),
        dbname=os.getenv("DB_NAME", "jeopardy"),
        user=os.getenv("DB_USER", "jeopardy"),
        password=os.getenv("DB_PASSWORD", "jeopardy"),
        sslmode=os.getenv("DB_SSLMODE", "disable"),
    )


def _fetch_random_clue(conn, round_filter: int | None):
    with conn.cursor() as cur:
        if round_filter is None:
            cur.execute(
                """
                SELECT c.id, cat.name, c.round, c.clue_value, c.answer, c.question, g.air_date
                FROM clues c
                JOIN categories cat ON cat.id = c.category_id
                JOIN games g ON g.id = c.game_id
                ORDER BY random()
                LIMIT 1
                """
            )
        else:
            cur.execute(
                """
                SELECT c.id, cat.name, c.round, c.clue_value, c.answer, c.question, g.air_date
                FROM clues c
                JOIN categories cat ON cat.id = c.category_id
                JOIN games g ON g.id = c.game_id
                WHERE c.round = %s
                ORDER BY random()
                LIMIT 1
                """,
                (round_filter,),
            )
        row = cur.fetchone()
    if not row:
        raise RuntimeError("No clues found in database.")
    return {
        "id": row[0],
        "category": row[1],
        "round": row[2],
        "value": row[3],
        "clue_text": row[4],
        "expected_response": row[5],
        "air_date": str(row[6]),
    }


def _ask_yes_no(prompt: str, default_no: bool = True) -> bool:
    raw = input(prompt).strip().lower()
    if not raw:
        return not default_no
    return raw in {"y", "yes"}


def _fetch_event_snapshot(conn, event_id: int):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                deterministic_stage,
                deterministic_decision,
                similarity_score,
                token_overlap_score,
                llm_invoked,
                llm_reason_code,
                llm_reason_text,
                decision_source,
                final_decision,
                latency_ms_total,
                latency_ms_deterministic,
                latency_ms_llm
            FROM answer_grading_events
            WHERE id = %s
            """,
            (event_id,),
        )
        return cur.fetchone()


def run_session(conn, round_filter: int | None, readonly: bool):
    if readonly:
        print("Mode: READONLY (every graded attempt will be rolled back)")
    while True:
        clue = _fetch_random_clue(conn, round_filter)
        print("\n--- Random Clue ---")
        print(
            f"Clue ID: {clue['id']} | Air Date: {clue['air_date']} | "
            f"Round: {clue['round']} | Value: {clue['value']}"
        )
        print(f"Category: {clue['category']}")
        print(f"Clue: {clue['clue_text']}")
        user_response = input("\nYour answer (or /quit): ").strip()
        if user_response.lower() in {"/quit", "quit", "q", "exit"}:
            break

        try:
            with conn.cursor() as cur:
                result = grade_and_record(
                    cur,
                    clue_id=clue["id"],
                    clue_text=clue["clue_text"],
                    expected_response=clue["expected_response"],
                    user_response=user_response,
                )
            event_row = _fetch_event_snapshot(conn, int(result["event_id"]))
            if readonly:
                conn.rollback()
            else:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        print("\n--- Initial Grading Event ---")
        print(f"Event ID: {result['event_id']}")
        print(f"Trace ID: {result['trace_id']}")
        print(f"Correct: {result['correct']}")
        print(f"Expected: {result['expected']}")
        print(f"LLM Invoked: {result['llm_invoked']}")
        if readonly:
            print("Persisted: no (rolled back)")

        if event_row:
            print(f"Deterministic Stage: {event_row[0]}")
            print(f"Deterministic Decision: {event_row[1]}")
            print(f"Similarity: {0.0 if event_row[2] is None else float(event_row[2]):.3f}")
            print(f"Token Overlap: {0.0 if event_row[3] is None else float(event_row[3]):.3f}")
            print(f"LLM Reason Code: {event_row[5]}")
            print(f"LLM Reason: {event_row[6]}")
            print(f"Decision Source: {event_row[7]}")
            print(f"Final Decision: {event_row[8]}")
            print(
                "Latency ms (total/deterministic/llm): "
                f"{event_row[9]}/{event_row[10]}/{event_row[11] if event_row[11] is not None else 0}"
            )

        if _ask_yes_no("\nTry another random clue? [Y/n]: ", default_no=False):
            continue
        break


def main():
    parser = argparse.ArgumentParser(
        description="Try the initial grading flow (deterministic + auto-LLM) on random clues."
    )
    parser.add_argument(
        "--database-url",
        help="Postgres URL. If omitted, DATABASE_URL or DB_* env vars are used.",
    )
    parser.add_argument(
        "--round",
        type=int,
        choices=[1, 2, 3],
        default=None,
        help="Optional round filter (1, 2, or 3).",
    )
    parser.add_argument(
        "--readonly",
        action="store_true",
        help="Run full grading flow but roll back each attempt (no DB writes persisted).",
    )
    args = parser.parse_args()

    _load_env_file(BACKEND_DIR / ".env")

    conn = _connect(args.database_url)
    try:
        run_session(conn, args.round, args.readonly)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
