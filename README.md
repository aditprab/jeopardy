# Jeopardy

Monorepo for a Jeopardy-style daily challenge product plus data ingestion tooling.

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

- Product and local development: [webapp/README.md](/Users/adithya/Desktop/jeopardy/webapp/README.md)
- Dataset and ingestion details: [dataset/README.md](/Users/adithya/Desktop/jeopardy/dataset/README.md)
- System behavior and grading flow: [docs/architecture.md](/Users/adithya/Desktop/jeopardy/docs/architecture.md)
- Runbook and troubleshooting: [docs/operations.md](/Users/adithya/Desktop/jeopardy/docs/operations.md)
- Future project conventions: [projects/README.md](/Users/adithya/Desktop/jeopardy/projects/README.md)
