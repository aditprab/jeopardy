# Webapp

Daily-challenge Jeopardy product.

## Scope

- Daily challenge only.
- Manual appeal UI is removed.
- Initial answer grading uses deterministic acceptance first, then auto-LLM judge for unresolved cases.

## Structure

- `frontend/`: React + Vite client.
- `backend/`: FastAPI service and grading logic.

## Backend Setup

```bash
cd webapp/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Required runtime env:

- `OPENAI_API_KEY`
- `JUDGE_MODEL` (default shown in example)
- `JUDGE_TIMEOUT_MS`
- database settings via `DATABASE_URL` or `DB_*`

Run backend:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Frontend Setup

```bash
cd webapp/frontend
npm install
cp .env.example .env
npm run dev
```

Build check:

```bash
npm run build
```

## Current API Surface

- `GET /api/daily-challenge`
- `POST /api/daily-challenge/answer`
- `POST /api/daily-challenge/final/wager`
- `POST /api/daily-challenge/final`
- `POST /api/daily-challenge/reset`

## Grading Persistence

Primary table for new submissions:

- `answer_grading_events`

Agent telemetry:

- `agent_runs`
- `agent_run_events`
- `agent_run_artifacts`

Legacy `answer_attempts` and `answer_appeals` are retained for audit/history only.
