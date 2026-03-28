from __future__ import annotations

from typing import Any

from ..agents.hint_context_classifier.agent import run_hint_context_classifier
from ..agents.hint_context_classifier.types import HintContextClassifierInput


def target(inputs: dict[str, Any]) -> dict[str, Any]:
    classification = run_hint_context_classifier(
        HintContextClassifierInput(
            clue_text=inputs["clue_text"],
            expected_response=inputs["expected_response"],
            category=inputs["category"],
            air_date=inputs["air_date"],
        )
    )
    return {
        "is_point_in_time": classification.is_point_in_time,
        "reason_code": classification.reason_code,
        "confidence": classification.confidence,
    }


def decision_correct(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> bool:
    return outputs["is_point_in_time"] == reference_outputs["is_point_in_time"]


def reason_code_correct(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> bool:
    expected = reference_outputs.get("reason_code")
    if expected is None:
        return True
    return outputs.get("reason_code") == expected
