# Operations

Runbook for local development and basic troubleshooting.

## Start Services

Database:

```bash
cd dataset
docker compose up -d
```

Backend:

```bash
cd webapp/backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd webapp/frontend
npm run dev
```

## Build/Compile Checks

Backend:

```bash
python3 -m compileall webapp/backend
```

Frontend:

```bash
cd webapp/frontend
npm run build
```

## Key Rotation

- Keep `OPENAI_API_KEY` out of version control.
- If a key is ever exposed in logs or docs, rotate immediately.

## SQL Checks for Grading Quality

LLM invocation rate:

```sql
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE llm_invoked) AS llm_invoked
FROM answer_grading_events
WHERE created_at >= NOW() - INTERVAL '7 days';
```

LLM failure rate (fail-closed path):

```sql
SELECT
  COUNT(*) FILTER (WHERE llm_reason_code = 'llm_unavailable_auto_reject') AS llm_fail_closed,
  COUNT(*) FILTER (WHERE llm_invoked) AS llm_invoked
FROM answer_grading_events
WHERE created_at >= NOW() - INTERVAL '7 days';
```

Latency snapshot:

```sql
SELECT
  ROUND(AVG(latency_ms_total)) AS avg_total_ms,
  ROUND(AVG(latency_ms_llm)) FILTER (WHERE llm_invoked) AS avg_llm_ms
FROM answer_grading_events
WHERE created_at >= NOW() - INTERVAL '7 days';
```

## Common Issues

- Backend starts but all LLM paths fallback quickly:
  - Verify `OPENAI_API_KEY` is loaded in the backend process environment.
- Frontend cannot reach backend:
  - Verify `VITE_API_BASE_URL` and backend port.
- Daily challenge appears stale:
  - Confirm DB writes in `daily_player_progress` and `answer_grading_events`.
