# LangSmith Evals

This repo now includes a minimal LangSmith eval scaffold for backend agents.

## Why this exists

It gives us a real eval workflow without forcing agent logic into LangSmith-specific code:

- local JSON files are the source of truth for test cases
- LangSmith datasets and experiments hold synced copies and experiment results
- agent target functions stay in regular Python modules

## Current shape

Code:

- `webapp/backend/evals/langsmith_cli.py`
- `webapp/backend/evals/langsmith_registry.py`
- `webapp/backend/evals/dataset_loader.py`
- `webapp/backend/evals/appeal_judge.py`

Starter dataset:

- `webapp/backend/evals/datasets/appeal_judge_v1.json`

## Environment

Set:

- `OPENAI_API_KEY`
- `LANGSMITH_API_KEY`
- `LANGSMITH_TRACING=true`
- `LANGSMITH_PROJECT=jeopardy-evals`

Optionally set:

- `LANGSMITH_ENDPOINT`

## Install

From `webapp/backend`:

```bash
pip install -r requirements.txt
```

## Sync local cases to LangSmith

```bash
cd /path/to/repo/root
python -m webapp.backend.evals.langsmith_cli sync appeal_judge_v1
```

This command:

1. loads the local JSON file
2. creates the dataset if needed
3. replaces existing examples in the LangSmith dataset
4. uploads the current local cases

## Run the eval

```bash
cd /path/to/repo/root
python -m webapp.backend.evals.langsmith_cli run appeal_judge_v1
```

Optional repetitions:

```bash
cd /path/to/repo/root
python -m webapp.backend.evals.langsmith_cli run appeal_judge_v1 --repetitions 3
```

## One-command script

You can also use:

```bash
/Users/adithya/Desktop/jeopardy/webapp/backend/evals/run_langsmith_eval.sh
```

Optional arguments:

```bash
/Users/adithya/Desktop/jeopardy/webapp/backend/evals/run_langsmith_eval.sh appeal_judge_v1 3
```

This script:

- loads `webapp/backend/.env` if present
- expects `LANGSMITH_API_KEY` and `OPENAI_API_KEY` in `webapp/backend/.env`
- syncs the dataset
- runs the LangSmith eval

## Adding cases

Edit `webapp/backend/evals/datasets/appeal_judge_v1.json`.

Each case uses:

- `inputs`: passed to the eval target function
- `outputs`: gold/reference outputs used by evaluators
- `metadata`: tags or notes for filtering in LangSmith

## Adding a new eval

1. Add a new JSON dataset under `webapp/backend/evals/datasets/`.
2. Add a target function and evaluators under `webapp/backend/evals/`.
3. Register it in `webapp/backend/evals/langsmith_registry.py`.
4. Run `sync` and then `run`.

## Notes

- LangSmith's `evaluate()` expects a target function plus evaluators. We use that directly.
- Datasets in LangSmith are versioned when examples are added, updated, or deleted.
- You can later bind evaluators to the dataset in the LangSmith UI if you want standard checks to run on every experiment.
