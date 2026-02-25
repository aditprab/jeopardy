# Dataset

Database bootstrap and ingestion tooling for Jeopardy source data.

## Contents

- `docker-compose.yml`: local Postgres service.
- `setup_db.py`: initial DB creation/connection setup.
- `schema.sql`: schema, indexes, and application tables.
- `load_data.py`: ingestion and cleanup from raw source files.
- `jeopardy_dataset_seasons_1-41/`: source dataset files.

## Source Dataset

- Source release: <https://github.com/jwolle1/jeopardy_clue_dataset/releases/tag/v41>

## Local Database Defaults

- Host: `localhost`
- Port: `5433`
- Database: `jeopardy`
- User: `jeopardy`
- Password: `jeopardy`

## Bootstrap Flow

From `dataset/`:

```bash
docker compose up -d
python setup_db.py
psql -h localhost -p 5433 -U jeopardy -d jeopardy -f schema.sql
python load_data.py
```

## Validation Checks

```bash
psql -h localhost -p 5433 -U jeopardy -d jeopardy -c "\dt"
psql -h localhost -p 5433 -U jeopardy -d jeopardy -c "SELECT COUNT(*) FROM clues;"
psql -h localhost -p 5433 -U jeopardy -d jeopardy -c "SELECT COUNT(*) FROM games;"
```

## Reset/Rebuild

If you want a clean local rebuild:

```bash
docker compose down -v
docker compose up -d
python setup_db.py
psql -h localhost -p 5433 -U jeopardy -d jeopardy -f schema.sql
python load_data.py
```

## Notes

- `schema.sql` includes the `answer_grading_events` table used by the app.
- Legacy answer attempt/appeal tables remain for history.

