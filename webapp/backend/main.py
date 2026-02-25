from contextlib import asynccontextmanager
import os
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    from .db import init_pool, close_pool
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
    from .grading import ensure_grading_schema
except ImportError:
    # Supports running from webapp/backend as module path "main:app".
    from db import init_pool, close_pool
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
    from grading import ensure_grading_schema


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


class DailyAnswerRequest(BaseModel):
    stage: str
    index: int
    response: str
    skipped: bool = False


class DailyFinalRequest(BaseModel):
    response: str


class DailyFinalWagerRequest(BaseModel):
    wager: int


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
