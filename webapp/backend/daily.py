from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from psycopg2.extras import Json

try:
    from .answer import check_answer
    from .db import get_conn, put_conn
except ImportError:
    from answer import check_answer
    from db import get_conn, put_conn

ET_TZ = ZoneInfo("America/New_York")
START_DATE = date(2005, 1, 1)

SINGLE_VALUES = [200, 400, 600, 800, 1000]
DOUBLE_VALUES = [400, 800, 1200, 1600, 2000]


@dataclass
class DailyChallenge:
    challenge_date: date
    single_category_name: str
    single_clue_ids: list[int]
    double_category_name: str
    double_clue_ids: list[int]
    final_category_name: str
    final_clue_id: int


DEFAULT_ANSWERS = {
    "single": [None, None, None, None, None],
    "double": [None, None, None, None, None],
}


def today_et() -> date:
    return datetime.now(ET_TZ).date()


def _copy_default_answers() -> dict[str, list[dict[str, Any] | None]]:
    return {
        "single": [None, None, None, None, None],
        "double": [None, None, None, None, None],
    }


def ensure_daily_schema() -> None:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_challenges (
                    challenge_date DATE PRIMARY KEY,
                    single_category_name TEXT NOT NULL,
                    single_clue_ids INT[] NOT NULL,
                    double_category_name TEXT NOT NULL,
                    double_clue_ids INT[] NOT NULL,
                    final_category_name TEXT NOT NULL,
                    final_clue_id INT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_player_progress (
                    id BIGSERIAL PRIMARY KEY,
                    challenge_date DATE NOT NULL REFERENCES daily_challenges(challenge_date) ON DELETE CASCADE,
                    player_token TEXT NOT NULL,
                    current_score INT NOT NULL DEFAULT 0,
                    answers_json JSONB NOT NULL,
                    final_attempt_id BIGINT REFERENCES answer_attempts(id),
                    final_wager INT,
                    final_response TEXT,
                    final_correct BOOLEAN,
                    final_expected_response TEXT,
                    final_score_delta INT,
                    completed_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE (challenge_date, player_token)
                )
                """
            )
            cur.execute(
                """
                ALTER TABLE daily_player_progress
                ADD COLUMN IF NOT EXISTS final_attempt_id BIGINT REFERENCES answer_attempts(id)
                """
            )
            cur.execute(
                """
                ALTER TABLE daily_player_progress
                ADD COLUMN IF NOT EXISTS final_wager INT
                """
            )
            cur.execute(
                """
                ALTER TABLE daily_player_progress
                ADD COLUMN IF NOT EXISTS final_response TEXT
                """
            )
            cur.execute(
                """
                ALTER TABLE daily_player_progress
                ADD COLUMN IF NOT EXISTS final_correct BOOLEAN
                """
            )
            cur.execute(
                """
                ALTER TABLE daily_player_progress
                ADD COLUMN IF NOT EXISTS final_expected_response TEXT
                """
            )
            cur.execute(
                """
                ALTER TABLE daily_player_progress
                ADD COLUMN IF NOT EXISTS final_score_delta INT
                """
            )
            cur.execute(
                """
                ALTER TABLE daily_player_progress
                ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_daily_progress_token
                ON daily_player_progress(player_token)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_daily_progress_challenge_date
                ON daily_player_progress(challenge_date)
                """
            )
        conn.commit()
    finally:
        put_conn(conn)


def _select_daily_game(cur, offset: int) -> int:
    cur.execute(
        """
        WITH round1_categories AS (
            SELECT
                c.game_id,
                c.category_id
            FROM clues c
            WHERE c.round = 1
            GROUP BY c.game_id, c.category_id
            HAVING COUNT(*) = 5
               AND ARRAY_AGG(c.clue_value ORDER BY c.clue_value) = %s::INT[]
        ),
        round1_valid AS (
            SELECT game_id, COUNT(*) AS cat_count
            FROM round1_categories
            GROUP BY game_id
        ),
        round2_categories AS (
            SELECT
                c.game_id,
                c.category_id
            FROM clues c
            WHERE c.round = 2
            GROUP BY c.game_id, c.category_id
            HAVING COUNT(*) = 5
               AND ARRAY_AGG(c.clue_value ORDER BY c.clue_value) = %s::INT[]
        ),
        round2_valid AS (
            SELECT game_id, COUNT(*) AS cat_count
            FROM round2_categories
            GROUP BY game_id
        ),
        eligible_games AS (
            SELECT
                g.id AS game_id,
                g.air_date,
                ROW_NUMBER() OVER (ORDER BY g.air_date ASC, g.id ASC) - 1 AS idx,
                COUNT(*) OVER () AS total
            FROM games g
            JOIN round1_valid r1 ON r1.game_id = g.id
            JOIN round2_valid r2 ON r2.game_id = g.id
            WHERE g.air_date >= %s
              AND r1.cat_count >= 6
              AND r2.cat_count >= 6
              AND EXISTS (
                  SELECT 1
                  FROM clues cf
                  WHERE cf.game_id = g.id
                    AND cf.round = 3
              )
        )
        SELECT game_id, total
        FROM eligible_games
        WHERE idx = (%s %% total)
        LIMIT 1
        """,
        (SINGLE_VALUES, DOUBLE_VALUES, START_DATE, offset),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError("No valid games found for daily challenge")
    return row[0]


def _select_category_for_game(
    cur,
    *,
    game_id: int,
    round_num: int,
    values: list[int],
) -> tuple[str, list[int]]:
    cur.execute(
        """
        WITH category_groups AS (
            SELECT
                cat.name,
                c.category_id,
                ARRAY_AGG(c.id ORDER BY c.clue_value) AS clue_ids
            FROM clues c
            JOIN categories cat ON cat.id = c.category_id
            WHERE c.game_id = %s
              AND c.round = %s
            GROUP BY cat.name, c.category_id
            HAVING COUNT(*) = 5
               AND ARRAY_AGG(c.clue_value ORDER BY c.clue_value) = %s::INT[]
        )
        SELECT name, clue_ids
        FROM category_groups
        ORDER BY category_id ASC
        LIMIT 1
        """,
        (game_id, round_num, values),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(f"No valid category found for round {round_num} in game {game_id}")
    return row[0], list(row[1])


def _select_final_for_game(cur, *, game_id: int) -> tuple[str, int]:
    cur.execute(
        """
        SELECT
            cat.name,
            c.id
        FROM clues c
        JOIN categories cat ON cat.id = c.category_id
        WHERE c.game_id = %s
          AND c.round = 3
        ORDER BY c.id ASC
        LIMIT 1
        """,
        (game_id,),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(f"No final clue found in game {game_id}")
    return row[0], row[1]


def get_or_create_daily_challenge(challenge_date: date) -> DailyChallenge:
    day_offset = max(0, (challenge_date - START_DATE).days)

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    challenge_date,
                    single_category_name,
                    single_clue_ids,
                    double_category_name,
                    double_clue_ids,
                    final_category_name,
                    final_clue_id
                FROM daily_challenges
                WHERE challenge_date = %s
                """,
                (challenge_date,),
            )
            row = cur.fetchone()
            if row:
                return DailyChallenge(
                    challenge_date=row[0],
                    single_category_name=row[1],
                    single_clue_ids=list(row[2]),
                    double_category_name=row[3],
                    double_clue_ids=list(row[4]),
                    final_category_name=row[5],
                    final_clue_id=row[6],
                )

            game_id = _select_daily_game(cur, offset=day_offset)
            single_name, single_ids = _select_category_for_game(
                cur,
                game_id=game_id,
                round_num=1,
                values=SINGLE_VALUES,
            )
            double_name, double_ids = _select_category_for_game(
                cur,
                game_id=game_id,
                round_num=2,
                values=DOUBLE_VALUES,
            )
            final_name, final_id = _select_final_for_game(cur, game_id=game_id)

            cur.execute(
                """
                INSERT INTO daily_challenges (
                    challenge_date,
                    single_category_name,
                    single_clue_ids,
                    double_category_name,
                    double_clue_ids,
                    final_category_name,
                    final_clue_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (challenge_date) DO NOTHING
                """,
                (challenge_date, single_name, single_ids, double_name, double_ids, final_name, final_id),
            )

            cur.execute(
                """
                SELECT
                    challenge_date,
                    single_category_name,
                    single_clue_ids,
                    double_category_name,
                    double_clue_ids,
                    final_category_name,
                    final_clue_id
                FROM daily_challenges
                WHERE challenge_date = %s
                """,
                (challenge_date,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("Failed to create daily challenge")
            conn.commit()
            return DailyChallenge(
                challenge_date=row[0],
                single_category_name=row[1],
                single_clue_ids=list(row[2]),
                double_category_name=row[3],
                double_clue_ids=list(row[4]),
                final_category_name=row[5],
                final_clue_id=row[6],
            )
    finally:
        put_conn(conn)


def _fetch_clues(cur, clue_ids: list[int]) -> dict[int, dict[str, Any]]:
    cur.execute(
        """
        SELECT c.id, c.clue_value, c.answer, c.question, g.air_date
        FROM clues c
        JOIN games g ON g.id = c.game_id
        WHERE c.id = ANY(%s::INT[])
        """,
        (clue_ids,),
    )
    by_id: dict[int, dict[str, Any]] = {}
    for clue_id, clue_value, clue_text, expected, air_date in cur.fetchall():
        by_id[clue_id] = {
            "id": clue_id,
            "value": clue_value,
            "clue_text": clue_text,
            "expected_response": expected,
            "air_date": air_date.isoformat(),
        }
    return by_id


def _load_or_create_progress(
    cur,
    challenge_date: date,
    player_token: str,
    *,
    for_update: bool = False,
) -> dict[str, Any]:
    lock_clause = "FOR UPDATE" if for_update else ""
    cur.execute(
        f"""
        SELECT id, current_score, answers_json, final_wager, final_response, final_correct,
               final_expected_response, final_score_delta, completed_at, final_attempt_id
        FROM daily_player_progress
        WHERE challenge_date = %s AND player_token = %s
        {lock_clause}
        """,
        (challenge_date, player_token),
    )
    row = cur.fetchone()
    if row:
        answers = row[2] if row[2] else _copy_default_answers()
        if "single" not in answers or "double" not in answers:
            answers = _copy_default_answers()
        return {
            "id": row[0],
            "current_score": row[1],
            "answers": answers,
            "final_wager": row[3],
            "final_response": row[4],
            "final_correct": row[5],
            "final_expected_response": row[6],
            "final_score_delta": row[7],
            "completed_at": row[8].isoformat() if row[8] else None,
            "final_attempt_id": row[9],
        }

    answers = _copy_default_answers()
    cur.execute(
        """
        INSERT INTO daily_player_progress (
            challenge_date,
            player_token,
            answers_json
        )
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (challenge_date, player_token, Json(answers)),
    )
    progress_id = cur.fetchone()[0]
    return {
        "id": progress_id,
        "current_score": 0,
        "answers": answers,
        "final_wager": None,
        "final_response": None,
        "final_correct": None,
        "final_expected_response": None,
        "final_score_delta": None,
        "completed_at": None,
        "final_attempt_id": None,
    }


def _serialize_progress(progress: dict[str, Any]) -> dict[str, Any]:
    return {
        "current_score": progress["current_score"],
        "answers": progress["answers"],
        "final": {
            "submitted": progress["completed_at"] is not None,
            "wager": progress["final_wager"],
            "response": progress["final_response"],
            "correct": progress["final_correct"],
            "expected": progress["final_expected_response"],
            "score_delta": progress["final_score_delta"],
            "completed_at": progress["completed_at"],
            "attempt_id": progress["final_attempt_id"],
        },
    }


def get_daily_challenge_payload(challenge: DailyChallenge, player_token: str) -> dict[str, Any]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            clue_map = _fetch_clues(cur, challenge.single_clue_ids + challenge.double_clue_ids + [challenge.final_clue_id])
            progress = _load_or_create_progress(cur, challenge.challenge_date, player_token, for_update=False)
            conn.commit()

        single_clues = [clue_map[cid] for cid in challenge.single_clue_ids]
        double_clues = [clue_map[cid] for cid in challenge.double_clue_ids]
        final_clue = clue_map[challenge.final_clue_id]

        final_clue_text = final_clue["clue_text"] if progress["final_wager"] is not None else None

        return {
            "challenge_date": challenge.challenge_date.isoformat(),
            "timezone": "America/New_York",
            "single_category": {
                "name": challenge.single_category_name,
                "clues": [
                    {
                        "id": c["id"],
                        "value": c["value"],
                        "clue_text": c["clue_text"],
                        "air_date": c["air_date"],
                    }
                    for c in single_clues
                ],
            },
            "double_category": {
                "name": challenge.double_category_name,
                "clues": [
                    {
                        "id": c["id"],
                        "value": c["value"],
                        "clue_text": c["clue_text"],
                        "air_date": c["air_date"],
                    }
                    for c in double_clues
                ],
            },
            "final_clue": {
                "id": final_clue["id"],
                "category": challenge.final_category_name,
                "clue_text": final_clue_text,
                "air_date": final_clue["air_date"],
            },
            "progress": _serialize_progress(progress),
        }
    finally:
        put_conn(conn)


def submit_daily_answer(
    *,
    challenge: DailyChallenge,
    player_token: str,
    stage: str,
    index: int,
    response_text: str,
    skipped: bool = False,
) -> dict[str, Any]:
    if stage not in ("single", "double"):
        raise ValueError("Stage must be 'single' or 'double'")
    if index < 0 or index > 4:
        raise ValueError("Index must be between 0 and 4")
    if not skipped and not response_text.strip():
        raise ValueError("Response cannot be empty")

    clue_ids = challenge.single_clue_ids if stage == "single" else challenge.double_clue_ids
    clue_id = clue_ids[index]

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            progress = _load_or_create_progress(cur, challenge.challenge_date, player_token, for_update=True)
            if progress["completed_at"]:
                raise ValueError("Daily challenge already completed")

            stage_answers = progress["answers"][stage]
            existing = stage_answers[index]
            if existing is not None:
                conn.commit()
                return {
                    "idempotent": True,
                    "stage": stage,
                    "index": index,
                    "clue_id": clue_id,
                    "attempt_id": existing.get("attempt_id"),
                    "correct": existing["correct"],
                    "skipped": existing.get("skipped", False),
                    "expected": existing["expected"],
                    "value": existing["value"],
                    "score_delta": existing["score_delta"],
                    "score_after": progress["current_score"],
                }

            clue_map = _fetch_clues(cur, [clue_id])
            clue = clue_map.get(clue_id)
            if not clue:
                raise ValueError("Clue not found")

            value = clue["value"]
            expected = clue["expected_response"]
            correct = False
            attempt_id = None
            if skipped:
                score_delta = 0
            else:
                correct, expected = check_answer(response_text, clue["expected_response"])
                score_delta = value if correct else -value
                cur.execute(
                    """
                    INSERT INTO answer_attempts (
                        clue_id,
                        user_response,
                        expected_response_snapshot,
                        fuzzy_correct
                    )
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (clue_id, response_text, expected, correct),
                )
                attempt_id = cur.fetchone()[0]
            new_score = progress["current_score"] + score_delta

            stage_answers[index] = {
                "clue_id": clue_id,
                "attempt_id": attempt_id,
                "response": response_text,
                "correct": correct,
                "skipped": skipped,
                "expected": expected,
                "value": value,
                "score_delta": score_delta,
            }

            cur.execute(
                """
                UPDATE daily_player_progress
                SET current_score = %s,
                    answers_json = %s,
                    updated_at = now()
                WHERE id = %s
                """,
                (new_score, Json(progress["answers"]), progress["id"]),
            )
            conn.commit()

            return {
                "idempotent": False,
                "stage": stage,
                "index": index,
                "clue_id": clue_id,
                "attempt_id": attempt_id,
                "correct": correct,
                "skipped": skipped,
                "expected": expected,
                "value": value,
                "score_delta": score_delta,
                "score_after": new_score,
            }
    finally:
        put_conn(conn)


def submit_daily_final_wager(
    *,
    challenge: DailyChallenge,
    player_token: str,
    wager: int,
) -> dict[str, Any]:
    if wager < 0:
        raise ValueError("Wager cannot be negative")

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            progress = _load_or_create_progress(cur, challenge.challenge_date, player_token, for_update=True)

            if progress["completed_at"]:
                conn.commit()
                return {
                    "idempotent": True,
                    "wager": progress["final_wager"],
                }

            if any(item is None for item in progress["answers"]["single"]) or any(
                item is None for item in progress["answers"]["double"]
            ):
                raise ValueError("All 10 clues must be answered before Final Jeopardy")

            current_score = progress["current_score"]
            max_wager = current_score if current_score >= 0 else 0
            if wager > max_wager:
                raise ValueError(f"Wager must be between 0 and {max_wager}")

            existing_wager = progress["final_wager"]
            if existing_wager is not None:
                conn.commit()
                return {
                    "idempotent": True,
                    "wager": existing_wager,
                }

            cur.execute(
                """
                UPDATE daily_player_progress
                SET final_wager = %s,
                    updated_at = now()
                WHERE id = %s
                """,
                (wager, progress["id"]),
            )
            conn.commit()
            return {
                "idempotent": False,
                "wager": wager,
            }
    finally:
        put_conn(conn)


def submit_daily_final(
    *,
    challenge: DailyChallenge,
    player_token: str,
    response_text: str,
) -> dict[str, Any]:
    if not response_text.strip():
        raise ValueError("Final response cannot be empty")

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            progress = _load_or_create_progress(cur, challenge.challenge_date, player_token, for_update=True)

            if progress["completed_at"]:
                conn.commit()
                return {
                    "idempotent": True,
                    "attempt_id": progress["final_attempt_id"],
                    "correct": progress["final_correct"],
                    "expected": progress["final_expected_response"],
                    "wager": progress["final_wager"],
                    "score_delta": progress["final_score_delta"],
                    "final_score": progress["current_score"],
                }

            if any(item is None for item in progress["answers"]["single"]) or any(
                item is None for item in progress["answers"]["double"]
            ):
                raise ValueError("All 10 clues must be answered before Final Jeopardy")

            wager = progress["final_wager"]
            if wager is None:
                raise ValueError("You must lock your wager before viewing Final Jeopardy")
            current_score = progress["current_score"]

            clue_map = _fetch_clues(cur, [challenge.final_clue_id])
            clue = clue_map.get(challenge.final_clue_id)
            if not clue:
                raise ValueError("Final clue not found")

            correct, expected = check_answer(response_text, clue["expected_response"])
            score_delta = wager if correct else -wager
            final_score = current_score + score_delta
            cur.execute(
                """
                INSERT INTO answer_attempts (
                    clue_id,
                    user_response,
                    expected_response_snapshot,
                    fuzzy_correct
                )
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (challenge.final_clue_id, response_text, expected, correct),
            )
            attempt_id = cur.fetchone()[0]

            cur.execute(
                """
                UPDATE daily_player_progress
                SET current_score = %s,
                    final_attempt_id = %s,
                    final_wager = %s,
                    final_response = %s,
                    final_correct = %s,
                    final_expected_response = %s,
                    final_score_delta = %s,
                    completed_at = now(),
                    updated_at = now()
                WHERE id = %s
                """,
                (
                    final_score,
                    attempt_id,
                    wager,
                    response_text,
                    correct,
                    expected,
                    score_delta,
                    progress["id"],
                ),
            )
            conn.commit()

            return {
                "idempotent": False,
                "attempt_id": attempt_id,
                "correct": correct,
                "expected": expected,
                "wager": wager,
                "score_delta": score_delta,
                "final_score": final_score,
            }
    finally:
        put_conn(conn)


def apply_daily_appeal(
    *,
    challenge: DailyChallenge,
    player_token: str,
    stage: str,
    index: int | None,
    attempt_id: int,
) -> dict[str, Any]:
    if stage not in ("single", "double", "final"):
        raise ValueError("Stage must be 'single', 'double', or 'final'")
    if stage in ("single", "double") and (index is None or index < 0 or index > 4):
        raise ValueError("Index must be between 0 and 4")
    if stage == "final" and index is not None:
        raise ValueError("Final appeal does not use an index")

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            progress = _load_or_create_progress(cur, challenge.challenge_date, player_token, for_update=True)
            answers = progress["answers"]

            if stage == "final":
                if progress["final_attempt_id"] != attempt_id:
                    raise ValueError("Attempt does not match this player's final clue")
            else:
                stage_answer = answers[stage][index]
                if not stage_answer:
                    raise ValueError("No answer recorded for this clue")
                if stage_answer.get("attempt_id") != attempt_id:
                    raise ValueError("Attempt does not match this player's clue answer")

            cur.execute(
                """
                SELECT ap.status, ap.final_correct, ap.overturn, ap.reason_code, ap.reason_text, ap.confidence
                FROM answer_appeals ap
                WHERE ap.answer_attempt_id = %s
                """,
                (attempt_id,),
            )
            appeal_row = cur.fetchone()
            if not appeal_row:
                raise ValueError("Appeal not found for this attempt")

            status, final_correct, overturn, reason_code, reason_text, confidence = appeal_row
            if status != "decided":
                raise ValueError("Appeal is not decided yet")
            if final_correct is None:
                raise ValueError("Appeal decision missing final correctness")

            score_delta_adjustment = 0
            updated_score = progress["current_score"]

            if stage == "final":
                prev_correct = progress["final_correct"]
                if prev_correct is None:
                    raise ValueError("Final answer was not submitted")
                if prev_correct != final_correct:
                    wager = progress["final_wager"] or 0
                    prev_delta = progress["final_score_delta"] or 0
                    new_delta = wager if final_correct else -wager
                    score_delta_adjustment = new_delta - prev_delta
                    updated_score = progress["current_score"] + score_delta_adjustment
                    cur.execute(
                        """
                        UPDATE daily_player_progress
                        SET current_score = %s,
                            final_correct = %s,
                            final_score_delta = %s,
                            updated_at = now()
                        WHERE id = %s
                        """,
                        (updated_score, final_correct, new_delta, progress["id"]),
                    )
            else:
                stage_answer = answers[stage][index]
                prev_correct = stage_answer["correct"]
                if prev_correct != final_correct:
                    value = stage_answer["value"]
                    prev_delta = stage_answer["score_delta"]
                    new_delta = value if final_correct else -value
                    score_delta_adjustment = new_delta - prev_delta
                    updated_score = progress["current_score"] + score_delta_adjustment
                    stage_answer["correct"] = final_correct
                    stage_answer["score_delta"] = new_delta
                    cur.execute(
                        """
                        UPDATE daily_player_progress
                        SET current_score = %s,
                            answers_json = %s,
                            updated_at = now()
                        WHERE id = %s
                        """,
                        (updated_score, Json(answers), progress["id"]),
                    )

            conn.commit()
            return {
                "stage": stage,
                "index": index,
                "attempt_id": attempt_id,
                "overturn": overturn,
                "final_correct": final_correct,
                "reason_code": reason_code,
                "reason": reason_text,
                "confidence": float(confidence or 0),
                "score_after": updated_score,
                "score_delta_adjustment": score_delta_adjustment,
            }
    finally:
        put_conn(conn)


def reset_daily_progress(*, challenge: DailyChallenge, player_token: str) -> dict[str, Any]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM daily_player_progress
                WHERE challenge_date = %s AND player_token = %s
                """,
                (challenge.challenge_date, player_token),
            )
            deleted = cur.rowcount
        conn.commit()
        return {"reset": True, "deleted_rows": deleted}
    finally:
        put_conn(conn)
