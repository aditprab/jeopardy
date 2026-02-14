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
uvicorn webapp.backend.main:app --reload
```

Runs on http://localhost:8000.

## Frontend

```sh
cd webapp/frontend
npm install
npm run dev
```

Runs on http://localhost:5173 and proxies `/api` requests to the backend.
