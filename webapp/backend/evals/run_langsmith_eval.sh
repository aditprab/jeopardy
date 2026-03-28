#!/bin/zsh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$BACKEND_DIR/../.." && pwd)"

DATASET_NAME="${1:-appeal_judge_v1}"
REPETITIONS="${2:-1}"

ENV_FILE="${BACKEND_DIR}/.env"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

if [[ -z "${LANGSMITH_API_KEY:-}" ]]; then
  echo "LANGSMITH_API_KEY is not set. Add it to ${ENV_FILE} before running."
  exit 1
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "OPENAI_API_KEY is not set. Add it to ${ENV_FILE} or export it before running."
  exit 1
fi

export LANGSMITH_TRACING="${LANGSMITH_TRACING:-true}"
export LANGSMITH_PROJECT="${LANGSMITH_PROJECT:-jeopardy-evals}"

cd "$REPO_ROOT"
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

echo "Syncing dataset: ${DATASET_NAME}"
python -m webapp.backend.evals.langsmith_cli sync "$DATASET_NAME"

echo "Running eval: ${DATASET_NAME} (repetitions=${REPETITIONS})"
python -m webapp.backend.evals.langsmith_cli run "$DATASET_NAME" --repetitions "$REPETITIONS"
