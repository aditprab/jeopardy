from __future__ import annotations

from typing import Any

from ..agents.appeal_judge.agent import run_appeal_judge
from ..agents.appeal_judge.types import AppealJudgeInput


def target(inputs: dict[str, Any]) -> dict[str, Any]:
    decision = run_appeal_judge(
        AppealJudgeInput(
            clue_text=inputs["clue_text"],
            expected_response=inputs["expected_response"],
            user_response=inputs["user_response"],
            user_justification=inputs.get("user_justification"),
        )
    )
    return {
        "final_correct": decision.final_correct,
        "reason_code": decision.reason_code,
        "confidence": decision.confidence,
    }


def decision_correct(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> bool:
    return outputs["final_correct"] == reference_outputs["final_correct"]


def reason_code_correct(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> bool:
    expected = reference_outputs.get("reason_code")
    if expected is None:
        return True
    return outputs.get("reason_code") == expected
