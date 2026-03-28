from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AppealJudgeInput:
    clue_text: str
    expected_response: str
    user_response: str
    user_justification: str | None


@dataclass
class AppealDecision:
    overturn: bool
    final_correct: bool
    reason_code: str
    reason: str
    confidence: float
    guardrail_flags: list[str]
    model: str
    prompt_version: str
    usage: dict[str, int]
    raw_output: dict[str, Any]


@dataclass(frozen=True)
class LLMJudgeFailure:
    error_type: str
    error_message: str


@dataclass(frozen=True)
class ObservedAppealJudgeResult:
    run_id: int
    latency_ms: int
    decision: AppealDecision | None
    failure: LLMJudgeFailure | None
