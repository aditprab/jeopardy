from __future__ import annotations

from time import perf_counter
from typing import Any

from psycopg2.extras import Json


class RunTimer:
    def __init__(self):
        self._start = perf_counter()

    def elapsed_ms(self) -> int:
        return int((perf_counter() - self._start) * 1000)


def create_agent_run(
    cur,
    *,
    trace_id: str,
    run_type: str,
    agent_name: str,
    agent_version: str,
    policy_version: str,
    input_payload: dict[str, Any],
    model: str | None = None,
    prompt_version: str | None = None,
) -> int:
    cur.execute(
        """
        INSERT INTO agent_runs (
            trace_id, run_type, agent_name, agent_version, policy_version,
            status, model, prompt_version, input_payload
        )
        VALUES (%s, %s, %s, %s, %s, 'started', %s, %s, %s)
        RETURNING id
        """,
        (
            trace_id,
            run_type,
            agent_name,
            agent_version,
            policy_version,
            model,
            prompt_version,
            Json(input_payload),
        ),
    )
    return cur.fetchone()[0]


def log_agent_event(
    cur,
    *,
    agent_run_id: int,
    event_type: str,
    level: str,
    message: str,
    payload: dict[str, Any] | None = None,
):
    cur.execute(
        """
        INSERT INTO agent_run_events (agent_run_id, event_type, level, message, payload)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (agent_run_id, event_type, level, message, Json(payload or {})),
    )


def add_agent_artifact(
    cur,
    *,
    agent_run_id: int,
    artifact_type: str,
    content: dict[str, Any],
):
    cur.execute(
        """
        INSERT INTO agent_run_artifacts (agent_run_id, artifact_type, content)
        VALUES (%s, %s, %s)
        """,
        (agent_run_id, artifact_type, Json(content)),
    )


def finish_agent_run(
    cur,
    *,
    agent_run_id: int,
    status: str,
    output_payload: dict[str, Any] | None,
    guardrail_flags: list[str] | None,
    latency_ms: int,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    error_message: str | None = None,
):
    cur.execute(
        """
        UPDATE agent_runs
           SET status = %s,
               output_payload = %s,
               guardrail_flags = %s,
               error_message = %s,
               prompt_tokens = %s,
               completion_tokens = %s,
               total_tokens = %s,
               latency_ms = %s,
               finished_at = now()
         WHERE id = %s
        """,
        (
            status,
            Json(output_payload) if output_payload is not None else None,
            Json(guardrail_flags or []),
            error_message,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            latency_ms,
            agent_run_id,
        ),
    )
