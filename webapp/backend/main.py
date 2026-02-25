from contextlib import asynccontextmanager
import os
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    from .db import init_pool, close_pool, get_conn, put_conn
    from .board import generate_board, get_clue
    from .daily import (
        ensure_daily_schema,
        get_daily_challenge_payload,
        get_or_create_daily_challenge,
        reset_daily_progress,
        submit_daily_answer,
        submit_daily_final,
        submit_daily_final_wager,
        today_et,
    )
    from .grading import ensure_grading_schema, grade_and_record
except ImportError:
    # Supports running from webapp/backend as module path "main:app".
    from db import init_pool, close_pool, get_conn, put_conn
    from board import generate_board, get_clue
    from daily import (
        ensure_daily_schema,
        get_daily_challenge_payload,
        get_or_create_daily_challenge,
        reset_daily_progress,
        submit_daily_answer,
        submit_daily_final,
        submit_daily_final_wager,
        today_et,
    )
    from grading import ensure_grading_schema, grade_and_record


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()
    ensure_grading_schema()
    ensure_daily_schema()
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
    expose_headers=["X-Player-Token"],
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

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            result = grade_and_record(
                cur,
                clue_id=req.clue_id,
                clue_text=clue_data["clue_text"],
                expected_response=clue_data["expected_response"],
                user_response=req.response,
            )
        conn.commit()
        return {
            "correct": result["correct"],
            "expected": result["expected"],
            "attempt_id": result["event_id"],
            "trace_id": result["trace_id"],
            "llm_invoked": result["llm_invoked"],
            "reason_code": result["reason_code"],
            "reason": result["reason"],
        }
    except Exception:
        conn.rollback()
        raise HTTPException(status_code=500, detail="Failed to grade answer")
    finally:
        put_conn(conn)


class AppealRequest(BaseModel):
    attempt_id: int
    user_justification: str | None = None


@app.post("/api/appeal")
def appeal(req: AppealRequest):
    raise HTTPException(
        status_code=410,
        detail="Manual appeals are deprecated. Answers are now auto-judged on initial submission.",
    )


class DailyAnswerRequest(BaseModel):
    stage: str
    index: int
    response: str
    skipped: bool = False


class DailyFinalRequest(BaseModel):
    response: str


class DailyFinalWagerRequest(BaseModel):
    wager: int


class DailyAppealApplyRequest(BaseModel):
    stage: str
    index: int | None = None
    attempt_id: int


@app.get("/api/daily-challenge")
def daily_challenge(
    response: Response,
    player_token: str | None = Header(default=None, alias="X-Player-Token"),
):
    token = (player_token or "").strip() or str(uuid4())
    challenge_date = today_et()
    try:
        challenge = get_or_create_daily_challenge(challenge_date)
        payload = get_daily_challenge_payload(challenge, token)
        response.headers["X-Player-Token"] = token
        return payload
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/daily-challenge/answer")
def daily_answer(
    req: DailyAnswerRequest,
    response: Response,
    player_token: str | None = Header(default=None, alias="X-Player-Token"),
):
    token = (player_token or "").strip() or str(uuid4())
    challenge_date = today_et()
    try:
        challenge = get_or_create_daily_challenge(challenge_date)
        result = submit_daily_answer(
            challenge=challenge,
            player_token=token,
            stage=req.stage,
            index=req.index,
            response_text=req.response,
            skipped=req.skipped,
        )
        response.headers["X-Player-Token"] = token
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/daily-challenge/final/wager")
def daily_final_wager(
    req: DailyFinalWagerRequest,
    response: Response,
    player_token: str | None = Header(default=None, alias="X-Player-Token"),
):
    token = (player_token or "").strip() or str(uuid4())
    challenge_date = today_et()
    try:
        challenge = get_or_create_daily_challenge(challenge_date)
        result = submit_daily_final_wager(
            challenge=challenge,
            player_token=token,
            wager=req.wager,
        )
        response.headers["X-Player-Token"] = token
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/daily-challenge/final")
def daily_final(
    req: DailyFinalRequest,
    response: Response,
    player_token: str | None = Header(default=None, alias="X-Player-Token"),
):
    token = (player_token or "").strip() or str(uuid4())
    challenge_date = today_et()
    try:
        challenge = get_or_create_daily_challenge(challenge_date)
        result = submit_daily_final(
            challenge=challenge,
            player_token=token,
            response_text=req.response,
        )
        response.headers["X-Player-Token"] = token
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/daily-challenge/apply-appeal")
def daily_apply_appeal(
    req: DailyAppealApplyRequest,
    response: Response,
    player_token: str | None = Header(default=None, alias="X-Player-Token"),
):
    raise HTTPException(
        status_code=410,
        detail="Manual appeal application is deprecated. Daily answers are auto-judged on initial submission.",
    )


@app.post("/api/daily-challenge/reset")
def daily_reset(
    response: Response,
    player_token: str | None = Header(default=None, alias="X-Player-Token"),
):
    token = (player_token or "").strip() or str(uuid4())
    challenge_date = today_et()
    try:
        challenge = get_or_create_daily_challenge(challenge_date)
        result = reset_daily_progress(challenge=challenge, player_token=token)
        response.headers["X-Player-Token"] = token
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
