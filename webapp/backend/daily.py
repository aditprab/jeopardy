from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from psycopg2.extras import Json

try:
    from .db import get_conn, put_conn
    from .grading import grade_and_record
except ImportError:
    from db import get_conn, put_conn
    from grading import grade_and_record

ET_TZ = ZoneInfo("America/New_York")
MIN_AIR_DATE = date(2005, 1, 1)

SINGLE_VALUES = [200, 400, 600, 800, 1000]
DOUBLE_VALUES = [400, 800, 1200, 1600, 2000]
LEADERBOARD_NAME_MAX_LENGTH = 32


@dataclass
class DailyChallenge:
    challenge_date: date
    single_category_name: str
    single_clue_ids: list[int]
    double_category_name: str
    double_clue_ids: list[int]
    final_category_name: str
    final_clue_id: int


@dataclass
class PlayerProfile:
    id: int
    player_token: str
    leaderboard_name: str | None


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
                CREATE TABLE IF NOT EXISTS player_profiles (
                    id BIGSERIAL PRIMARY KEY,
                    player_token TEXT NOT NULL UNIQUE,
                    leaderboard_name TEXT,
                    auth_provider TEXT,
                    auth_subject TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE (auth_provider, auth_subject)
                )
                """
            )
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
                    final_attempt_id BIGINT,
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
                DROP CONSTRAINT IF EXISTS daily_player_progress_final_attempt_id_fkey
                """
            )
            cur.execute(
                """
                ALTER TABLE daily_player_progress
                ADD COLUMN IF NOT EXISTS final_attempt_id BIGINT
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
            cur.execute(
                """
                ALTER TABLE daily_player_progress
                ADD COLUMN IF NOT EXISTS player_id BIGINT REFERENCES player_profiles(id)
                """
            )
            cur.execute(
                """
                INSERT INTO player_profiles (player_token)
                SELECT DISTINCT dpp.player_token
                FROM daily_player_progress dpp
                LEFT JOIN player_profiles pp ON pp.player_token = dpp.player_token
                WHERE pp.id IS NULL
                """
            )
            cur.execute(
                """
                UPDATE daily_player_progress dpp
                SET player_id = pp.id
                FROM player_profiles pp
                WHERE dpp.player_id IS NULL
                  AND pp.player_token = dpp.player_token
                """
            )
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_progress_challenge_player
                ON daily_player_progress(challenge_date, player_id)
                WHERE player_id IS NOT NULL
                """
            )
            cur.execute(
                """
                ALTER TABLE daily_challenges
                ADD COLUMN IF NOT EXISTS single_game_id INT REFERENCES games(id)
                """
            )
            cur.execute(
                """
                ALTER TABLE daily_challenges
                ADD COLUMN IF NOT EXISTS single_category_id INT REFERENCES categories(id)
                """
            )
            cur.execute(
                """
                ALTER TABLE daily_challenges
                ADD COLUMN IF NOT EXISTS double_game_id INT REFERENCES games(id)
                """
            )
            cur.execute(
                """
                ALTER TABLE daily_challenges
                ADD COLUMN IF NOT EXISTS double_category_id INT REFERENCES categories(id)
                """
            )
            cur.execute(
                """
                ALTER TABLE daily_challenges
                ADD COLUMN IF NOT EXISTS final_game_id INT REFERENCES games(id)
                """
            )
            cur.execute(
                """
                ALTER TABLE daily_challenges
                ADD COLUMN IF NOT EXISTS final_category_id INT REFERENCES categories(id)
                """
            )
        conn.commit()
    finally:
        put_conn(conn)


def _load_used_pair_keys(cur) -> list[str]:
    cur.execute(
        """
        SELECT
            COALESCE(
                ARRAY_AGG(DISTINCT (c.game_id::TEXT || ':' || c.category_id::TEXT)),
                ARRAY[]::TEXT[]
            ) AS used_pair_keys
        FROM daily_challenges dc
        JOIN LATERAL unnest(
            dc.single_clue_ids
            || dc.double_clue_ids
            || ARRAY[dc.final_clue_id]
        ) AS used_clue(clue_id) ON TRUE
        JOIN clues c ON c.id = used_clue.clue_id
        """
    )
    row = cur.fetchone()
    return list(row[0] or [])


def _pick_random_category(
    cur,
    *,
    round_num: int,
    values: list[int],
    excluded_pair_keys: list[str],
) -> tuple[int, int, str, list[int]]:
    cur.execute(
        """
        SELECT
            c.game_id,
            c.category_id,
            cat.name,
            ARRAY_AGG(c.id ORDER BY c.clue_value) AS clue_ids
        FROM clues c
        JOIN categories cat ON cat.id = c.category_id
        JOIN games g ON g.id = c.game_id
        WHERE c.round = %s
          AND g.air_date >= %s
          AND NOT ((c.game_id::TEXT || ':' || c.category_id::TEXT) = ANY(%s::TEXT[]))
        GROUP BY c.game_id, c.category_id, cat.name
        HAVING COUNT(*) = 5
           AND ARRAY_AGG(c.clue_value ORDER BY c.clue_value) = %s::INT[]
        ORDER BY random()
        LIMIT 1
        """,
        (round_num, MIN_AIR_DATE, excluded_pair_keys, values),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(f"No unused category found for round {round_num}")
    return int(row[0]), int(row[1]), row[2], list(row[3])


def _pick_random_final(
    cur,
    *,
    excluded_pair_keys: list[str],
) -> tuple[int, int, str, int]:
    cur.execute(
        """
        SELECT
            c.game_id,
            c.category_id,
            cat.name,
            c.id
        FROM clues c
        JOIN categories cat ON cat.id = c.category_id
        JOIN games g ON g.id = c.game_id
        WHERE c.round = 3
          AND g.air_date >= %s
          AND NOT ((c.game_id::TEXT || ':' || c.category_id::TEXT) = ANY(%s::TEXT[]))
        ORDER BY random()
        LIMIT 1
        """,
        (MIN_AIR_DATE, excluded_pair_keys),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError("No unused Final Jeopardy clue found")
    return int(row[0]), int(row[1]), row[2], int(row[3])


def get_or_create_daily_challenge(challenge_date: date) -> DailyChallenge:
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

            # Serialize challenge creation so we do not accidentally reuse the same
            # game/category across dates under concurrent requests.
            cur.execute("LOCK TABLE daily_challenges IN SHARE ROW EXCLUSIVE MODE")

            used_pair_keys = _load_used_pair_keys(cur)
            single_game_id, single_category_id, single_name, single_ids = _pick_random_category(
                cur,
                round_num=1,
                values=SINGLE_VALUES,
                excluded_pair_keys=used_pair_keys,
            )
            used_pair_keys.append(f"{single_game_id}:{single_category_id}")

            double_game_id, double_category_id, double_name, double_ids = _pick_random_category(
                cur,
                round_num=2,
                values=DOUBLE_VALUES,
                excluded_pair_keys=used_pair_keys,
            )
            used_pair_keys.append(f"{double_game_id}:{double_category_id}")

            final_game_id, final_category_id, final_name, final_id = _pick_random_final(
                cur,
                excluded_pair_keys=used_pair_keys,
            )

            cur.execute(
                """
                INSERT INTO daily_challenges (
                    challenge_date,
                    single_category_name,
                    single_clue_ids,
                    single_game_id,
                    single_category_id,
                    double_category_name,
                    double_clue_ids,
                    double_game_id,
                    double_category_id,
                    final_category_name,
                    final_clue_id,
                    final_game_id,
                    final_category_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (challenge_date) DO NOTHING
                """,
                (
                    challenge_date,
                    single_name,
                    single_ids,
                    single_game_id,
                    single_category_id,
                    double_name,
                    double_ids,
                    double_game_id,
                    double_category_id,
                    final_name,
                    final_id,
                    final_game_id,
                    final_category_id,
                ),
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


def _normalize_leaderboard_name(value: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError("Leaderboard name is required")
    if len(normalized) > LEADERBOARD_NAME_MAX_LENGTH:
        raise ValueError(f"Leaderboard name must be {LEADERBOARD_NAME_MAX_LENGTH} characters or fewer")
    return normalized


def _load_or_create_player_profile(cur, player_token: str, *, for_update: bool = False) -> PlayerProfile:
    lock_clause = "FOR UPDATE" if for_update else ""
    cur.execute(
        f"""
        SELECT id, player_token, leaderboard_name
        FROM player_profiles
        WHERE player_token = %s
        {lock_clause}
        """,
        (player_token,),
    )
    row = cur.fetchone()
    if row:
        return PlayerProfile(
            id=int(row[0]),
            player_token=row[1],
            leaderboard_name=row[2],
        )

    cur.execute(
        """
        INSERT INTO player_profiles (player_token)
        VALUES (%s)
        ON CONFLICT (player_token)
        DO UPDATE SET updated_at = player_profiles.updated_at
        RETURNING id, player_token, leaderboard_name
        """,
        (player_token,),
    )
    row = cur.fetchone()
    return PlayerProfile(
        id=int(row[0]),
        player_token=row[1],
        leaderboard_name=row[2],
    )


def _load_or_create_progress(
    cur,
    challenge_date: date,
    player_profile: PlayerProfile,
    *,
    for_update: bool = False,
) -> dict[str, Any]:
    lock_clause = "FOR UPDATE" if for_update else ""
    cur.execute(
        f"""
        SELECT id, current_score, answers_json, final_wager, final_response, final_correct,
               final_expected_response, final_score_delta, completed_at, final_attempt_id, player_id
        FROM daily_player_progress
        WHERE challenge_date = %s
          AND (player_id = %s OR player_token = %s)
        ORDER BY CASE WHEN player_id = %s THEN 0 ELSE 1 END
        LIMIT 1
        {lock_clause}
        """,
        (challenge_date, player_profile.id, player_profile.player_token, player_profile.id),
    )
    row = cur.fetchone()
    if row:
        answers = row[2] if row[2] else _copy_default_answers()
        if "single" not in answers or "double" not in answers:
            answers = _copy_default_answers()
        if row[10] != player_profile.id:
            cur.execute(
                """
                UPDATE daily_player_progress
                SET player_id = %s,
                    updated_at = now()
                WHERE id = %s
                """,
                (player_profile.id, row[0]),
            )
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
            player_id,
            player_token,
            answers_json
        )
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (challenge_date, player_profile.id, player_profile.player_token, Json(answers)),
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


def _serialize_player_profile(profile: PlayerProfile) -> dict[str, Any]:
    return {
        "leaderboard_name": profile.leaderboard_name,
        "has_leaderboard_name": profile.leaderboard_name is not None,
    }


def get_daily_challenge_payload(challenge: DailyChallenge, player_token: str) -> dict[str, Any]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            player_profile = _load_or_create_player_profile(cur, player_token, for_update=False)
            clue_map = _fetch_clues(cur, challenge.single_clue_ids + challenge.double_clue_ids + [challenge.final_clue_id])
            progress = _load_or_create_progress(cur, challenge.challenge_date, player_profile, for_update=False)
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
            "player": _serialize_player_profile(player_profile),
            "progress": _serialize_progress(progress),
        }
    finally:
        put_conn(conn)


def upsert_player_profile(player_token: str, leaderboard_name: str) -> dict[str, Any]:
    normalized_name = _normalize_leaderboard_name(leaderboard_name)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO player_profiles (player_token, leaderboard_name)
                VALUES (%s, %s)
                ON CONFLICT (player_token)
                DO UPDATE SET leaderboard_name = EXCLUDED.leaderboard_name,
                              updated_at = now()
                RETURNING id, player_token, leaderboard_name
                """,
                (player_token, normalized_name),
            )
            row = cur.fetchone()
        conn.commit()
        return {
            "player": _serialize_player_profile(
                PlayerProfile(
                    id=int(row[0]),
                    player_token=row[1],
                    leaderboard_name=row[2],
                )
            )
        }
    finally:
        put_conn(conn)


def get_daily_leaderboard(challenge_date: date, player_token: str) -> dict[str, Any]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            player_profile = _load_or_create_player_profile(cur, player_token, for_update=False)
            cur.execute(
                """
                SELECT
                    dpp.player_id,
                    COALESCE(NULLIF(pp.leaderboard_name, ''), 'Anonymous'),
                    dpp.current_score,
                    dpp.completed_at,
                    dpp.updated_at
                FROM daily_player_progress dpp
                JOIN player_profiles pp ON pp.id = dpp.player_id
                WHERE dpp.challenge_date = %s
                  AND dpp.completed_at IS NOT NULL
                ORDER BY dpp.current_score DESC, dpp.completed_at ASC, dpp.id ASC
                LIMIT 25
                """,
                (challenge_date,),
            )
            rows = cur.fetchall()
            entries: list[dict[str, Any]] = []
            current_player_entry: dict[str, Any] | None = None
            for idx, row in enumerate(rows, start=1):
                entry = {
                    "rank": idx,
                    "player_name": row[1],
                    "score": row[2],
                    "completed_at": row[3].isoformat() if row[3] else None,
                    "is_current_player": row[0] == player_profile.id,
                }
                entries.append(entry)
                if entry["is_current_player"]:
                    current_player_entry = entry

            if current_player_entry is None:
                cur.execute(
                    """
                    SELECT current_score, completed_at
                    FROM daily_player_progress
                    WHERE challenge_date = %s
                      AND player_id = %s
                      AND completed_at IS NOT NULL
                    """,
                    (challenge_date, player_profile.id),
                )
                row = cur.fetchone()
                if row:
                    cur.execute(
                        """
                        SELECT COUNT(*) + 1
                        FROM daily_player_progress
                        WHERE challenge_date = %s
                          AND completed_at IS NOT NULL
                          AND (
                              current_score > %s
                              OR (current_score = %s AND completed_at < %s)
                          )
                        """,
                        (challenge_date, row[0], row[0], row[1]),
                    )
                    rank = int(cur.fetchone()[0])
                    current_player_entry = {
                        "rank": rank,
                        "player_name": player_profile.leaderboard_name or "Anonymous",
                        "score": row[0],
                        "completed_at": row[1].isoformat() if row[1] else None,
                        "is_current_player": True,
                    }
            conn.commit()
            return {
                "challenge_date": challenge_date.isoformat(),
                "entries": entries,
                "current_player_entry": current_player_entry,
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
            player_profile = _load_or_create_player_profile(cur, player_token, for_update=True)
            progress = _load_or_create_progress(
                cur,
                challenge.challenge_date,
                player_profile,
                for_update=True,
            )
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
                grade = grade_and_record(
                    cur,
                    challenge_date=challenge.challenge_date.isoformat(),
                    player_token=player_token,
                    clue_id=clue_id,
                    clue_text=clue["clue_text"],
                    expected_response=clue["expected_response"],
                    user_response=response_text,
                )
                correct = bool(grade["correct"])
                expected = grade["expected"]
                score_delta = value if correct else -value
                attempt_id = int(grade["event_id"])
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
            player_profile = _load_or_create_player_profile(cur, player_token, for_update=True)
            progress = _load_or_create_progress(
                cur,
                challenge.challenge_date,
                player_profile,
                for_update=True,
            )

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
            player_profile = _load_or_create_player_profile(cur, player_token, for_update=True)
            progress = _load_or_create_progress(
                cur,
                challenge.challenge_date,
                player_profile,
                for_update=True,
            )

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

            grade = grade_and_record(
                cur,
                challenge_date=challenge.challenge_date.isoformat(),
                player_token=player_token,
                clue_id=challenge.final_clue_id,
                clue_text=clue["clue_text"],
                expected_response=clue["expected_response"],
                user_response=response_text,
            )
            correct = bool(grade["correct"])
            expected = grade["expected"]
            score_delta = wager if correct else -wager
            final_score = current_score + score_delta
            attempt_id = int(grade["event_id"])

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
