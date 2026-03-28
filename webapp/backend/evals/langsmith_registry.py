from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from . import appeal_judge


TargetFn = Callable[[dict[str, Any]], dict[str, Any]]
EvaluatorFn = Callable[..., Any]


@dataclass(frozen=True)
class EvalDefinition:
    dataset_name: str
    target: TargetFn
    evaluators: list[EvaluatorFn]
    experiment_prefix: str


EVALS: dict[str, EvalDefinition] = {
    "appeal_judge_v1": EvalDefinition(
        dataset_name="appeal_judge_v1",
        target=appeal_judge.target,
        evaluators=[
            appeal_judge.decision_correct,
            appeal_judge.reason_code_correct,
        ],
        experiment_prefix="appeal-judge",
    )
}


def get_eval_definition(name: str) -> EvalDefinition:
    try:
        return EVALS[name]
    except KeyError as exc:
        known = ", ".join(sorted(EVALS))
        raise ValueError(f"Unknown eval dataset '{name}'. Known datasets: {known}") from exc
