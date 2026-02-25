from __future__ import annotations

import re
from time import perf_counter
from typing import Any
from uuid import uuid4

from thefuzz import fuzz

try:
    from .agent_observability import (
        add_agent_artifact,
        create_agent_run,
        finish_agent_run,
        log_agent_event,
    )
    from .answer import check_answer, extract_alternates, normalize
    from .appeal_judge import (
        AGENT_NAME,
        AGENT_VERSION,
        POLICY_VERSION,
        judge_appeal_llm_only,
    )
    from .db import get_conn, put_conn
except ImportError:
    from agent_observability import (
        add_agent_artifact,
        create_agent_run,
        finish_agent_run,
        log_agent_event,
    )
    from answer import check_answer, extract_alternates, normalize
    from appeal_judge import AGENT_NAME, AGENT_VERSION, POLICY_VERSION, judge_appeal_llm_only
    from db import get_conn, put_conn

PAREN_OR = re.compile(r"\(\s*or\b", re.IGNORECASE)
TOKEN_RE = re.compile(r"[a-z0-9]+")
NUMERIC_LIST_RE = re.compile(r"^\s*\d+(?:\s*[,/-]\s*\d+)+\s*$")


def ensure_grading_schema() -> None:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS answer_grading_events (
                    id BIGSERIAL PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    challenge_date DATE,
                    player_token TEXT,
                    clue_id INT NOT NULL REFERENCES clues(id),
                    user_response_raw TEXT NOT NULL,
                    expected_response_snapshot TEXT NOT NULL,
                    user_response_normalized TEXT NOT NULL,
                    expected_response_normalized TEXT NOT NULL,
                    deterministic_stage TEXT NOT NULL CHECK (
                        deterministic_stage IN ('exact', 'normalized', 'variant', 'none')
                    ),
                    deterministic_decision TEXT NOT NULL CHECK (
                        deterministic_decision IN ('accept', 'reject', 'defer_to_llm')
                    ),
                    similarity_score REAL,
                    token_overlap_score REAL,
                    has_parenthetical_or BOOLEAN NOT NULL DEFAULT FALSE,
                    looks_like_person_name BOOLEAN NOT NULL DEFAULT FALSE,
                    llm_invoked BOOLEAN NOT NULL DEFAULT FALSE,
                    llm_run_id BIGINT REFERENCES agent_runs(id),
                    llm_confidence NUMERIC(4,3),
                    llm_reason_code TEXT,
                    llm_reason_text TEXT,
                    final_decision TEXT NOT NULL CHECK (final_decision IN ('correct', 'incorrect')),
                    decision_source TEXT NOT NULL CHECK (decision_source IN ('deterministic', 'llm')),
                    overturn_of_event_id BIGINT REFERENCES answer_grading_events(id),
                    latency_ms_total INT NOT NULL,
                    latency_ms_deterministic INT NOT NULL,
                    latency_ms_llm INT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_age_clue_created
                ON answer_grading_events(clue_id, created_at DESC)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_age_player_date
                ON answer_grading_events(challenge_date, player_token)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_age_final_source
                ON answer_grading_events(final_decision, decision_source)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_age_llm_invoked
                ON answer_grading_events(llm_invoked)
                """
            )
        conn.commit()
    finally:
        put_conn(conn)


def _looks_like_person_name(expected: str) -> bool:
    for alt in extract_alternates(expected):
        words = [w for w in re.split(r"\s+", alt.strip()) if w]
        if len(words) >= 2 and all(any(ch.isalpha() for ch in w) for w in words):
            return True
    return False


def _token_overlap_score(a: str, b: str) -> float:
    a_tokens = set(TOKEN_RE.findall(a))
    b_tokens = set(TOKEN_RE.findall(b))
    if not a_tokens or not b_tokens:
        return 0.0
    overlap = len(a_tokens & b_tokens)
    return overlap / max(len(a_tokens), len(b_tokens))


def _similarity_score(user_norm: str, expected: str) -> float:
    best = 0.0
    for alt in extract_alternates(expected):
        alt_norm = normalize(alt)
        if not alt_norm:
            continue
        ratio = fuzz.ratio(user_norm, alt_norm) / 100.0
        token_ratio = fuzz.token_sort_ratio(user_norm, alt_norm) / 100.0
        best = max(best, ratio, token_ratio)
    return best


def _parse_numeric_list(text: str) -> list[str] | None:
    if not NUMERIC_LIST_RE.match(text):
        return None
    return sorted(re.findall(r"\d+", text))


def _deterministic_decision(
    *,
    user_response: str,
    expected_response: str,
) -> tuple[bool, str, str]:
    user_norm = normalize(user_response)
    if not user_norm:
        return False, "none", "reject"

    alt_norms = [normalize(alt) for alt in extract_alternates(expected_response)]
    if user_norm in alt_norms:
        return True, "exact", "accept"

    user_nums = _parse_numeric_list(user_norm)
    if user_nums is not None:
        for alt_norm in alt_norms:
            alt_nums = _parse_numeric_list(alt_norm)
            if alt_nums is not None and user_nums == alt_nums:
                return True, "variant", "accept"

    fuzzy_correct, _ = check_answer(user_response, expected_response)
    if fuzzy_correct:
        return True, "normalized", "accept"

    return False, "none", "defer_to_llm"


def grade_and_record(
    cur,
    *,
    clue_id: int,
    clue_text: str,
    expected_response: str,
    user_response: str,
    challenge_date: str | None = None,
    player_token: str | None = None,
) -> dict[str, Any]:
    total_start = perf_counter()
    trace_id = str(uuid4())

    user_norm = normalize(user_response)
    expected_norm = normalize(expected_response)
    has_parenthetical_or = bool(PAREN_OR.search(expected_response))
    looks_like_person_name = _looks_like_person_name(expected_response)
    similarity = _similarity_score(user_norm, expected_response) if user_norm else 0.0
    overlap = _token_overlap_score(user_norm, expected_norm) if user_norm else 0.0

    det_start = perf_counter()
    det_correct, det_stage, det_decision = _deterministic_decision(
        user_response=user_response,
        expected_response=expected_response,
    )
    det_latency_ms = int((perf_counter() - det_start) * 1000)

    llm_invoked = False
    llm_run_id: int | None = None
    llm_confidence: float | None = None
    llm_reason_code: str | None = None
    llm_reason_text: str | None = None
    llm_latency_ms: int | None = None
    final_correct = det_correct
    decision_source = "deterministic"

    if det_decision == "defer_to_llm":
        llm_invoked = True
        llm_start = perf_counter()
        llm_run_id = create_agent_run(
            cur,
            trace_id=trace_id,
            run_type="initial_answer_judge",
            agent_name=AGENT_NAME,
            agent_version=AGENT_VERSION,
            policy_version=POLICY_VERSION,
            model=None,
            prompt_version=None,
            input_payload={
                "clue_id": clue_id,
                "user_response": user_response,
                "expected_response": expected_response,
            },
        )
        log_agent_event(
            cur,
            agent_run_id=llm_run_id,
            event_type="initial_answer_received",
            level="info",
            message="Initial answer sent to judge after deterministic defer.",
                payload={"clue_id": clue_id},
            )
        decision, llm_failure = judge_appeal_llm_only(
            clue_text=clue_text,
            expected_response=expected_response,
            user_response=user_response,
            user_justification=None,
        )
        llm_latency_ms = int((perf_counter() - llm_start) * 1000)
        if decision is not None:
            decision_source = "llm"
            final_correct = decision.final_correct
            llm_confidence = decision.confidence
            llm_reason_code = decision.reason_code
            llm_reason_text = decision.reason
            cur.execute(
                "UPDATE agent_runs SET model = %s, prompt_version = %s WHERE id = %s",
                (decision.model, decision.prompt_version, llm_run_id),
            )
            add_agent_artifact(
                cur,
                agent_run_id=llm_run_id,
                artifact_type="decision",
                content={
                    "final_correct": decision.final_correct,
                    "reason_code": decision.reason_code,
                    "reason": decision.reason,
                    "confidence": decision.confidence,
                },
            )
            add_agent_artifact(
                cur,
                agent_run_id=llm_run_id,
                artifact_type="model_output",
                content=decision.raw_output,
            )
            finish_agent_run(
                cur,
                agent_run_id=llm_run_id,
                status="completed",
                output_payload={
                    "final_correct": decision.final_correct,
                    "reason_code": decision.reason_code,
                    "reason": decision.reason,
                    "confidence": decision.confidence,
                },
                guardrail_flags=decision.guardrail_flags,
                prompt_tokens=decision.usage.get("prompt_tokens"),
                completion_tokens=decision.usage.get("completion_tokens"),
                total_tokens=decision.usage.get("total_tokens"),
                latency_ms=llm_latency_ms,
            )
        else:
            # Caller-owned fail-closed policy for LLM outages/errors.
            decision_source = "deterministic"
            final_correct = False
            llm_confidence = 0.0
            llm_reason_code = "llm_unavailable_auto_reject"
            llm_reason_text = (
                f"LLM judge failed ({llm_failure.error_type if llm_failure else 'UnknownError'}); "
                "auto-rejected by caller policy."
            )
            log_agent_event(
                cur,
                agent_run_id=llm_run_id,
                event_type="initial_answer_llm_failed",
                level="warn",
                message="LLM judge failed; caller applied fail-closed rejection.",
                payload={
                    "error_type": llm_failure.error_type if llm_failure else "UnknownError",
                    "error_message": llm_failure.error_message if llm_failure else "",
                },
            )
            finish_agent_run(
                cur,
                agent_run_id=llm_run_id,
                status="failed",
                output_payload={
                    "final_correct": False,
                    "reason_code": llm_reason_code,
                    "reason": llm_reason_text,
                },
                guardrail_flags=[
                    "llm_unavailable_auto_reject",
                    llm_failure.error_type if llm_failure else "UnknownError",
                ],
                error_message=llm_failure.error_message if llm_failure else "LLM judge failed",
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                latency_ms=llm_latency_ms,
            )

    final_decision = "correct" if final_correct else "incorrect"
    total_latency_ms = int((perf_counter() - total_start) * 1000)
    cur.execute(
        """
        INSERT INTO answer_grading_events (
            trace_id,
            challenge_date,
            player_token,
            clue_id,
            user_response_raw,
            expected_response_snapshot,
            user_response_normalized,
            expected_response_normalized,
            deterministic_stage,
            deterministic_decision,
            similarity_score,
            token_overlap_score,
            has_parenthetical_or,
            looks_like_person_name,
            llm_invoked,
            llm_run_id,
            llm_confidence,
            llm_reason_code,
            llm_reason_text,
            final_decision,
            decision_source,
            latency_ms_total,
            latency_ms_deterministic,
            latency_ms_llm
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s
        )
        RETURNING id
        """,
        (
            trace_id,
            challenge_date,
            player_token,
            clue_id,
            user_response,
            expected_response,
            user_norm,
            expected_norm,
            det_stage,
            det_decision,
            similarity,
            overlap,
            has_parenthetical_or,
            looks_like_person_name,
            llm_invoked,
            llm_run_id,
            llm_confidence,
            llm_reason_code,
            llm_reason_text,
            final_decision,
            decision_source,
            total_latency_ms,
            det_latency_ms,
            llm_latency_ms,
        ),
    )
    event_id = cur.fetchone()[0]
    return {
        "event_id": event_id,
        "trace_id": trace_id,
        "correct": final_correct,
        "expected": expected_response,
        "llm_invoked": llm_invoked,
        "reason_code": llm_reason_code,
        "reason": llm_reason_text,
    }
