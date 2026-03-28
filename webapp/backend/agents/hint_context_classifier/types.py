from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HintContextClassifierInput:
    clue_text: str
    expected_response: str
    category: str
    air_date: str


@dataclass
class HintContextClassification:
    is_point_in_time: bool
    reason_code: str
    reason: str
    confidence: float
    guardrail_flags: list[str]
    model: str
    prompt_version: str
    usage: dict[str, int]
    raw_output: dict[str, Any]


@dataclass(frozen=True)
class LLMHintContextFailure:
    error_type: str
    error_message: str


@dataclass(frozen=True)
class ObservedHintContextClassifierResult:
    run_id: int
    latency_ms: int
    classification: HintContextClassification | None
    failure: LLMHintContextFailure | None
