# Architecture

System currently serves the daily challenge product only.

## Components

- Frontend (`webapp/frontend`): React/Vite UI for daily play.
- Backend (`webapp/backend`): FastAPI endpoints and grading logic.
- Postgres: gameplay state, grading events, and agent telemetry.

## Runtime Flow

1. Client fetches daily challenge payload.
2. Client submits answers (`single`, `double`, `final`).
3. Backend grades submission and writes one `answer_grading_events` row.
4. Backend updates `daily_player_progress`.
5. Client reads updated score/progress.

## Grading Decision Tree

For each submission:

1. Normalize text and compute grading signals.
2. Deterministic accept if:
- exact normalized alternate match
- numeric-list variant match
- legacy fuzzy matcher (`check_answer`) passes
3. Deterministic reject if normalized input is blank.
4. Otherwise defer to LLM judge.
5. If LLM succeeds, use LLM decision.
6. If LLM fails, caller applies fail-closed policy: incorrect.

## Persistence Model

Primary grading table:

- `answer_grading_events`

Daily progress/state:

- `daily_challenges`
- `daily_player_progress`

Agent observability:

- `agent_runs`
- `agent_run_events`
- `agent_run_artifacts`

Legacy tables retained for audit only:

- `answer_attempts`
- `answer_appeals`

## API Surface (Daily Only)

- `GET /api/daily-challenge`
- `POST /api/daily-challenge/answer`
- `POST /api/daily-challenge/final/wager`
- `POST /api/daily-challenge/final`
- `POST /api/daily-challenge/reset`
