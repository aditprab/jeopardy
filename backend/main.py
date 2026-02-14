from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.db import init_pool, close_pool
from backend.board import generate_board, get_clue
from backend.answer import check_answer


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()
    yield
    close_pool()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    return {"correct": correct, "expected": expected}
