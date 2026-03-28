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

Precompute a future daily challenge:

```bash
python webapp/backend/scripts/precompute_daily_challenge.py
```

That script:

- defaults to `tomorrow` in `America/New_York`
- creates the daily challenge if missing
- fills any missing hint-context classifier cache rows for its clues

Useful variants:

```bash
python webapp/backend/scripts/precompute_daily_challenge.py --date today
python webapp/backend/scripts/precompute_daily_challenge.py --date 2026-03-29
```

Recommended cron timing for launch-day traffic:

```cron
55 23 * * * cd /path/to/repo/root && /usr/bin/env python3 webapp/backend/scripts/precompute_daily_challenge.py
```

Protected internal precompute endpoint:

```bash
curl -X POST http://localhost:8000/internal/precompute-daily-challenge \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: $INTERNAL_API_TOKEN" \
  -d '{"date":"tomorrow"}'
```

The `date` field accepts `today`, `tomorrow`, or `YYYY-MM-DD`.

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
