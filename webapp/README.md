# Webapp

Jeopardy web app — FastAPI backend + React/Vite frontend.

## Prerequisites

- Python 3.11+ with a virtual env (repo root `.venv/`)
- Node.js 18+
- Postgres running (see `docker-compose.yml` at repo root)

## Backend

From the repo root:

```sh
source .venv/bin/activate
pip install -r webapp/backend/requirements.txt
cp webapp/backend/.env.example webapp/backend/.env
# edit webapp/backend/.env with real values
uvicorn webapp.backend.main:app --reload --env-file webapp/backend/.env
```

Runs on http://localhost:8000.

## Deploy Data To Railway (Postgres)

From repo root, clone local DB -> Railway DB:

```sh
.venv/bin/python webapp/backend/deploy/export_local_to_remote.py \
  --target-url "postgresql://...railway..." \
  --drop-target \
  --yes
```

Notes:
- `--drop-target` is destructive on the target DB.
- Script requires `pg_dump` and `psql` installed.

## Deploy To Railway

Deploy backend and frontend as two separate Railway services from this repo.

### Backend service

- Railway config file path: `webapp/backend/railway.toml`

- Required env vars:
  - `DATABASE_URL` (from Railway Postgres)
  - `DB_SSLMODE=require` (recommended if not already present in URL query)
  - `OPENAI_API_KEY`
  - `JUDGE_MODEL` (optional)
  - `JUDGE_TIMEOUT_MS` (optional)
  - `CORS_ORIGINS` (set to frontend Railway URL, comma-separated if multiple)

### Frontend service

- Railway config file path: `webapp/frontend/railway.toml`

- Required env vars:
  - `VITE_API_BASE_URL` = your backend Railway public URL

## Frontend

```sh
cd webapp/frontend
npm install
npm run dev
```

Runs on http://localhost:5173 and proxies `/api` requests to the backend.
