# Jeopardy

Using a Jeopardy question/answer dataset, started off with an LLM-backed "Daily Challenge" web app. 
This repo contains that app, base data ingestion scripts, and eventually data analysis scripts.

## Repository Layout

- `webapp/`: consumer-facing application (frontend + backend APIs).
- `dataset/`: Postgres schema, setup, and ingestion scripts from source Jeopardy data.
- `docs/`: architecture and operations docs.
- `projects/`: future standalone data science or experimentation projects.

## Quick Start

1. Start Postgres (from `dataset/`):
```bash
cd dataset
docker compose up -d
```

2. Bootstrap and load data:
```bash
python setup_db.py
psql -h localhost -p 5433 -U jeopardy -d jeopardy -f schema.sql
python load_data.py
```

3. Start backend:
```bash
cd ../webapp/backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

4. Start frontend:
```bash
cd ../frontend
npm install
npm run dev
```

Frontend defaults to Vite local host; set `VITE_API_BASE_URL` if needed.

## Read Next

- Product and local development: [webapp/README.md](webapp/README.md)
- Dataset and ingestion details: [dataset/README.md](dataset/README.md)
- System behavior and grading flow: [docs/architecture.md](docs/architecture.md)
- Runbook and troubleshooting: [docs/operations.md](docs/operations.md)
- Future project conventions: [projects/README.md](projects/README.md)
