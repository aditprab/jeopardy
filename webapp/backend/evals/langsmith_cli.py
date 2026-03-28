from __future__ import annotations

import argparse
import os
from typing import Any

from .dataset_loader import load_local_dataset
from .langsmith_registry import get_eval_definition

try:
    from langsmith import Client, evaluate
except ImportError as exc:  # pragma: no cover - import is environment-dependent
    raise RuntimeError(
        "langsmith is required for eval commands. Install backend requirements first."
    ) from exc


def _client() -> Client:
    return Client()


def _get_or_create_dataset(client: Client, dataset_name: str, description: str):
    existing = next(client.list_datasets(dataset_name=dataset_name), None)
    if existing is not None:
        return existing
    return client.create_dataset(dataset_name=dataset_name, description=description)


def _dataset_examples_payload(local_dataset) -> list[dict[str, Any]]:
    return [
        {
            "inputs": case.inputs,
            "outputs": case.outputs,
            "metadata": case.metadata,
        }
        for case in local_dataset.cases
    ]


def sync_dataset(dataset_name: str) -> None:
    client = _client()
    local_dataset = load_local_dataset(dataset_name)
    dataset = _get_or_create_dataset(
        client,
        dataset_name=local_dataset.dataset_name,
        description=local_dataset.description,
    )

    existing_examples = list(client.list_examples(dataset_id=dataset.id))
    for example in existing_examples:
        client.delete_example(example.id)

    for example in _dataset_examples_payload(local_dataset):
        client.create_example(
            inputs=example["inputs"],
            outputs=example["outputs"],
            metadata=example["metadata"],
            dataset_id=dataset.id,
        )
    print(
        f"Synced dataset '{local_dataset.dataset_name}' with {len(local_dataset.cases)} examples."
    )


def run_eval(dataset_name: str, *, num_repetitions: int = 1) -> None:
    definition = get_eval_definition(dataset_name)
    experiment_prefix = definition.experiment_prefix
    if project := os.getenv("LANGSMITH_PROJECT"):
        experiment_prefix = f"{project}-{experiment_prefix}"

    results = evaluate(
        definition.target,
        data=definition.dataset_name,
        evaluators=definition.evaluators,
        experiment_prefix=experiment_prefix,
        num_repetitions=num_repetitions,
    )
    print(f"Started experiment for dataset '{definition.dataset_name}'.")
    experiment_name = getattr(results, "experiment_name", None)
    if experiment_name:
        print(f"Experiment: {experiment_name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="LangSmith eval utilities for Jeopardy agents")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser("sync", help="Sync a local JSON dataset to LangSmith")
    sync_parser.add_argument("dataset_name", help="Local dataset name, for example appeal_judge_v1")

    run_parser = subparsers.add_parser("run", help="Run a LangSmith experiment for a dataset")
    run_parser.add_argument("dataset_name", help="Dataset/eval name, for example appeal_judge_v1")
    run_parser.add_argument("--repetitions", type=int, default=1, help="Number of repetitions")

    args = parser.parse_args()
    if args.command == "sync":
        sync_dataset(args.dataset_name)
        return
    if args.command == "run":
        run_eval(args.dataset_name, num_repetitions=args.repetitions)
        return
    raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
