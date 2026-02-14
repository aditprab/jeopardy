from contextlib import asynccontextmanager
import os
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .db import init_pool, close_pool
from .board import generate_board, get_clue
from .answer import check_answer
from .appeal_judge import (
    AGENT_NAME,
    AGENT_VERSION,
    POLICY_VERSION,
    judge_appeal,
)
from .agent_observability import (
    RunTimer,
    add_agent_artifact,
    create_agent_run,
    finish_agent_run,
    log_agent_event,
)
from .db import get_conn, put_conn


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()
    yield
    close_pool()


app = FastAPI(lifespan=lifespan)

cors_origins_raw = os.getenv("CORS_ORIGINS", "*").strip()
cors_origins = (
    ["*"]
    if cors_origins_raw == "*"
    else [origin.strip() for origin in cors_origins_raw.split(",") if origin.strip()]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/board")
def board(round: int = Query(..., ge=1, le=2)):
    try:
        return generate_board(round)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/clue/{clue_id}")
def clue(clue_id: int):
    result = get_clue(clue_id)
    if not result:
        raise HTTPException(status_code=404, detail="Clue not found")
    return result


class AnswerRequest(BaseModel):
    clue_id: int
    response: str


@app.post("/api/answer")
def answer(req: AnswerRequest):
    clue_data = get_clue(req.clue_id)
    if not clue_data:
        raise HTTPException(status_code=404, detail="Clue not found")

    correct, expected = check_answer(req.response, clue_data["expected_response"])
    attempt_id = None
    conn = get_conn()
    try:
        with conn.cursor() as cur:
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
                (req.clue_id, req.response, expected, correct),
            )
            attempt_id = cur.fetchone()[0]
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        put_conn(conn)
    return {"correct": correct, "expected": expected, "attempt_id": attempt_id}


class AppealRequest(BaseModel):
    attempt_id: int
    user_justification: str | None = None


@app.post("/api/appeal")
def appeal(req: AppealRequest):
    conn = get_conn()
    trace_id = str(uuid4())
    timer = RunTimer()
    run_id = None
    appeal_id = None

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT a.id, a.clue_id, a.user_response, a.expected_response_snapshot, a.fuzzy_correct, c.answer
                  FROM answer_attempts a
                  JOIN clues c ON c.id = a.clue_id
                 WHERE a.id = %s
                """,
                (req.attempt_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Answer attempt not found")

            attempt_id, clue_id, user_response, expected, fuzzy_correct, clue_text = row

            cur.execute(
                """
                SELECT ap.id, ap.status, ap.final_correct, ap.overturn, ap.reason_code, ap.reason_text, ap.confidence, ar.trace_id
                  FROM answer_appeals ap
             LEFT JOIN agent_runs ar ON ar.id = ap.agent_run_id
                 WHERE ap.answer_attempt_id = %s
                """,
                (attempt_id,),
            )
            existing = cur.fetchone()
            if existing and existing[1] == "decided":
                return {
                    "appeal_id": existing[0],
                    "final_correct": existing[2],
                    "overturn": existing[3],
                    "reason_code": existing[4],
                    "reason": existing[5],
                    "confidence": float(existing[6] or 0),
                    "expected": expected,
                    "trace_id": existing[7] or trace_id,
                    "status": "decided",
                }

            if existing:
                appeal_id = existing[0]
            else:
                cur.execute(
                    """
                    INSERT INTO answer_appeals (answer_attempt_id, status, user_justification)
                    VALUES (%s, 'pending', %s)
                    RETURNING id
                    """,
                    (attempt_id, req.user_justification),
                )
                appeal_id = cur.fetchone()[0]

            run_id = create_agent_run(
                cur,
                trace_id=trace_id,
                run_type="answer_appeal",
                agent_name=AGENT_NAME,
                agent_version=AGENT_VERSION,
                policy_version=POLICY_VERSION,
                model=None,
                prompt_version=None,
                input_payload={
                    "appeal_id": appeal_id,
                    "attempt_id": attempt_id,
                    "clue_id": clue_id,
                    "user_response": user_response,
                    "expected_response": expected,
                    "fuzzy_correct": fuzzy_correct,
                    "user_justification": req.user_justification or "",
                },
            )
            log_agent_event(
                cur,
                agent_run_id=run_id,
                event_type="appeal_received",
                level="info",
                message="Appeal request accepted for judging.",
                payload={"appeal_id": appeal_id, "attempt_id": attempt_id},
            )

            decision = judge_appeal(
                clue_text=clue_text,
                expected_response=expected,
                user_response=user_response,
                fuzzy_correct=fuzzy_correct,
                user_justification=req.user_justification,
            )
            cur.execute(
                "UPDATE agent_runs SET model = %s, prompt_version = %s WHERE id = %s",
                (decision.model, decision.prompt_version, run_id),
            )

            add_agent_artifact(
                cur,
                agent_run_id=run_id,
                artifact_type="decision",
                content={
                    "overturn": decision.overturn,
                    "final_correct": decision.final_correct,
                    "reason_code": decision.reason_code,
                    "reason": decision.reason,
                    "confidence": decision.confidence,
                },
            )
            add_agent_artifact(
                cur,
                agent_run_id=run_id,
                artifact_type="model_output",
                content=decision.raw_output,
            )
            log_agent_event(
                cur,
                agent_run_id=run_id,
                event_type="appeal_decided",
                level="info",
                message="Appeal decision generated.",
                payload={
                    "overturn": decision.overturn,
                    "reason_code": decision.reason_code,
                    "confidence": decision.confidence,
                },
            )
            if "llm_fallback" in decision.guardrail_flags:
                log_agent_event(
                    cur,
                    agent_run_id=run_id,
                    event_type="appeal_fallback",
                    level="warn",
                    message="LLM unavailable or invalid output; deterministic fallback used.",
                    payload={
                        "guardrail_flags": decision.guardrail_flags,
                        "llm_error_type": decision.raw_output.get("llm_error_type"),
                        "llm_error_message": decision.raw_output.get("llm_error_message"),
                    },
                )

            finish_agent_run(
                cur,
                agent_run_id=run_id,
                status="completed",
                output_payload={
                    "overturn": decision.overturn,
                    "final_correct": decision.final_correct,
                    "reason_code": decision.reason_code,
                    "reason": decision.reason,
                    "confidence": decision.confidence,
                },
                guardrail_flags=decision.guardrail_flags,
                prompt_tokens=decision.usage.get("prompt_tokens"),
                completion_tokens=decision.usage.get("completion_tokens"),
                total_tokens=decision.usage.get("total_tokens"),
                latency_ms=timer.elapsed_ms(),
            )
            cur.execute(
                """
                UPDATE answer_appeals
                   SET status = 'decided',
                       agent_run_id = %s,
                       overturn = %s,
                       final_correct = %s,
                       reason_code = %s,
                       reason_text = %s,
                       confidence = %s,
                       decided_at = now()
                 WHERE id = %s
                """,
                (
                    run_id,
                    decision.overturn,
                    decision.final_correct,
                    decision.reason_code,
                    decision.reason,
                    decision.confidence,
                    appeal_id,
                ),
            )
            conn.commit()
            return {
                "appeal_id": appeal_id,
                "final_correct": decision.final_correct,
                "overturn": decision.overturn,
                "reason_code": decision.reason_code,
                "reason": decision.reason,
                "confidence": decision.confidence,
                "expected": expected,
                "trace_id": trace_id,
                "status": "decided",
            }
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        if run_id is not None:
            with conn.cursor() as cur:
                finish_agent_run(
                    cur,
                    agent_run_id=run_id,
                    status="failed",
                    output_payload=None,
                    guardrail_flags=["internal_error_fallback"],
                    error_message=str(exc),
                    latency_ms=timer.elapsed_ms(),
                )
                if appeal_id is not None:
                    cur.execute(
                        """
                        UPDATE answer_appeals
                           SET status = 'error',
                               agent_run_id = %s,
                               reason_code = 'internal_error',
                               reason_text = %s,
                               decided_at = now()
                         WHERE id = %s
                        """,
                        (run_id, str(exc), appeal_id),
                    )
                conn.commit()
        raise HTTPException(status_code=500, detail="Appeal judge failed")
    finally:
        put_conn(conn)
