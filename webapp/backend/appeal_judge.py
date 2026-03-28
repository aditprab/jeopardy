from __future__ import annotations

try:
    from .agents.appeal_judge import (
        AGENT_NAME,
        AGENT_VERSION,
        POLICY_VERSION,
        PROMPT_VERSION,
        AppealDecision,
        LLMJudgeFailure,
        ObservedAppealJudgeResult,
        judge_appeal,
        judge_appeal_llm_only,
        judge_appeal_llm_only_observed,
    )
except ImportError:
    from agents.appeal_judge import (  # type: ignore[no-redef]
        AGENT_NAME,
        AGENT_VERSION,
        POLICY_VERSION,
        PROMPT_VERSION,
        AppealDecision,
        LLMJudgeFailure,
        ObservedAppealJudgeResult,
        judge_appeal,
        judge_appeal_llm_only,
        judge_appeal_llm_only_observed,
    )

__all__ = [
    "AGENT_NAME",
    "AGENT_VERSION",
    "POLICY_VERSION",
    "PROMPT_VERSION",
    "AppealDecision",
    "LLMJudgeFailure",
    "ObservedAppealJudgeResult",
    "judge_appeal",
    "judge_appeal_llm_only",
    "judge_appeal_llm_only_observed",
]
