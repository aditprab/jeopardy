from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LocalEvalCase:
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class LocalEvalDataset:
    dataset_name: str
    description: str
    agent_name: str
    cases: list[LocalEvalCase]
