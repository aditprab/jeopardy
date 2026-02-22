#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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
    from ..answer import check_answer
    from ..appeal_judge import judge_appeal
except ImportError:
    from answer import check_answer
    from appeal_judge import judge_appeal


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


def run_session(conn, round_filter: int | None):
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

        correct, expected = check_answer(user_response, clue["expected_response"])
        print("\n--- Initial Grader ---")
        print(f"Correct: {correct}")
        print(f"Expected: {expected}")

        if not _ask_yes_no("\nRun appeal judge for this response? [y/N]: "):
            if _ask_yes_no("Try another random clue? [Y/n]: ", default_no=False):
                continue
            break

        justification = input("Optional appeal note (press Enter to skip): ").strip()
        decision = judge_appeal(
            clue_text=clue["clue_text"],
            expected_response=expected,
            user_response=user_response,
            fuzzy_correct=correct,
            user_justification=justification or None,
        )

        print("\n--- Appeal Judge Decision ---")
        print(f"Overturn: {decision.overturn}")
        print(f"Final Correct: {decision.final_correct}")
        print(f"Reason Code: {decision.reason_code}")
        print(f"Confidence: {decision.confidence:.3f}")
        print(f"Reason: {decision.reason}")
        if decision.guardrail_flags:
            print(f"Guardrails: {', '.join(decision.guardrail_flags)}")
        else:
            print("Guardrails: (none)")

        if _ask_yes_no("\nShow raw model output payload? [y/N]: "):
            print(json.dumps(decision.raw_output, indent=2, sort_keys=True))

        if _ask_yes_no("\nTry another random clue? [Y/n]: ", default_no=False):
            continue
        break


def main():
    parser = argparse.ArgumentParser(
        description="Try the answer grader + appeal judge on random clues from your database."
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
    args = parser.parse_args()

    _load_env_file(BACKEND_DIR / ".env")

    conn = _connect(args.database_url)
    try:
        run_session(conn, args.round)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
