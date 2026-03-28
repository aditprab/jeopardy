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
        get_daily_leaderboard,
        get_or_create_daily_challenge,
        precompute_daily_challenge,
        reset_daily_progress,
        resolve_challenge_date,
        submit_daily_answer,
        submit_daily_final,
        submit_daily_final_wager,
        today_et,
        upsert_player_profile,
    )
    from .grading import ensure_grading_schema
except ImportError:
    # Supports running from webapp/backend as module path "main:app".
    from db import init_pool, close_pool
    from daily import (
        ensure_daily_schema,
        get_daily_challenge_payload,
        get_daily_leaderboard,
        get_or_create_daily_challenge,
        precompute_daily_challenge,
        reset_daily_progress,
        resolve_challenge_date,
        submit_daily_answer,
        submit_daily_final,
        submit_daily_final_wager,
        today_et,
        upsert_player_profile,
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


class PlayerProfileRequest(BaseModel):
    leaderboard_name: str


class InternalPrecomputeDailyChallengeRequest(BaseModel):
    date: str = "tomorrow"


def _require_internal_token(token: str | None) -> None:
    expected = os.getenv("INTERNAL_API_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=500, detail="INTERNAL_API_TOKEN is not configured")
    if (token or "").strip() != expected:
        raise HTTPException(status_code=403, detail="Forbidden")


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


@app.post("/internal/precompute-daily-challenge")
def internal_precompute_daily_challenge(
    req: InternalPrecomputeDailyChallengeRequest,
    internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
):
    _require_internal_token(internal_token)
    try:
        target_date = resolve_challenge_date(req.date)
        return precompute_daily_challenge(target_date)
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


@app.get("/api/daily-challenge/leaderboard")
def daily_leaderboard(
    response: Response,
    player_token: str | None = Header(default=None, alias="X-Player-Token"),
):
    token = (player_token or "").strip() or str(uuid4())
    challenge_date = today_et()
    try:
        challenge = get_or_create_daily_challenge(challenge_date)
        result = get_daily_leaderboard(challenge.challenge_date, token)
        response.headers["X-Player-Token"] = token
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/player-profile")
def update_player_profile(
    req: PlayerProfileRequest,
    response: Response,
    player_token: str | None = Header(default=None, alias="X-Player-Token"),
):
    token = (player_token or "").strip() or str(uuid4())
    try:
        result = upsert_player_profile(token, req.leaderboard_name)
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
