from __future__ import annotations

import json
from pathlib import Path

from .types import LocalEvalCase, LocalEvalDataset


DATASETS_DIR = Path(__file__).resolve().parent / "datasets"


def dataset_path(dataset_name: str) -> Path:
    return DATASETS_DIR / f"{dataset_name}.json"


def load_local_dataset(dataset_name: str) -> LocalEvalDataset:
    path = dataset_path(dataset_name)
    payload = json.loads(path.read_text())
    cases = [
        LocalEvalCase(
            inputs=case["inputs"],
            outputs=case["outputs"],
            metadata=case.get("metadata", {}),
        )
        for case in payload["cases"]
    ]
    return LocalEvalDataset(
        dataset_name=payload["dataset_name"],
        description=payload.get("description", ""),
        agent_name=payload["agent_name"],
        cases=cases,
    )
