from __future__ import annotations

import logging
import re
from time import perf_counter

from thefuzz import fuzz

try:
    from ...agent_observability import (
        add_agent_artifact,
        create_agent_run,
        finish_agent_run,
        log_agent_event,
    )
    from ...answer import extract_alternates, normalize
except ImportError:
    from agent_observability import add_agent_artifact, create_agent_run, finish_agent_run, log_agent_event
    from answer import extract_alternates, normalize

from ..runtime import AgentSpec, JsonSchemaRequest, OpenAIJsonSchemaRunner
from .prompt import build_system_prompt, build_user_prompt
from .types import AppealDecision, AppealJudgeInput, LLMJudgeFailure, ObservedAppealJudgeResult

AGENT_NAME = "appeal_judge"
AGENT_VERSION = "v5"
POLICY_VERSION = "appeal_policy_v5"
PROMPT_VERSION = "appeal_prompt_v3"

DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_TIMEOUT_MS = 7000
MIN_JUSTIFICATION_LEN = 280
HIGH_CONFIDENCE_THRESHOLD = 0.85
SAME_ENTITY_THRESHOLD = 0.9
FUZZ_THRESHOLD = 88
MAX_REASON_CHARS = 600

PERSON_INDICATORS = (
    " he ",
    " she ",
    " his ",
    " her ",
    "actor",
    "author",
    "poet",
    "scientist",
    "president",
    "king",
    "queen",
    "emperor",
    "composer",
    "inventor",
)
HONORIFICS = {"mr", "mrs", "ms", "miss", "dr", "sir", "st", "saint"}
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
ALLOWED_REASON_CODES = {
    "already_correct",
    "empty_response",
    "exact_match",
    "last_name_match",
    "minor_typo_match",
    "insufficient_specificity",
    "strong_fuzzy_match",
    "no_match",
    "semantic_equivalence",
}
ALLOWED_MATCH_TYPES = {"exact", "alias", "last_name", "minor_typo", "no_match"}
ACCEPT_REASON_CODES = {
    "exact_match",
    "last_name_match",
    "minor_typo_match",
    "strong_fuzzy_match",
    "semantic_equivalence",
}
REJECT_REASON_CODES = {"empty_response", "insufficient_specificity", "no_match"}
SPEC = AgentSpec(
    name=AGENT_NAME,
    version=AGENT_VERSION,
    policy_version=POLICY_VERSION,
    prompt_version=PROMPT_VERSION,
)

logger = logging.getLogger(__name__)


def _default_runner() -> OpenAIJsonSchemaRunner:
    return OpenAIJsonSchemaRunner(
        default_model=DEFAULT_MODEL,
        model_env_var="JUDGE_MODEL",
        timeout_env_var="JUDGE_TIMEOUT_MS",
        default_timeout_ms=DEFAULT_TIMEOUT_MS,
    )


def _looks_like_person_clue(clue_text: str) -> bool:
    text = f" {clue_text.lower()} "
    return any(indicator in text for indicator in PERSON_INDICATORS)


def _expected_last_name(expected: str) -> str | None:
    cleaned = expected.replace(",", " ").replace(".", " ")
    tokens = [t.strip().lower() for t in cleaned.split() if t.strip()]
    tokens = [t for t in tokens if t not in HONORIFICS]
    while tokens and tokens[-1] in SUFFIXES:
        tokens.pop()
    if len(tokens) < 2:
        return None
    return tokens[-1]


def _single_token(text: str) -> str | None:
    norm = normalize(text)
    parts = norm.split()
    if len(parts) == 2 and parts[0] in HONORIFICS:
        return parts[1]
    if len(parts) == 1:
        return parts[0]
    return None


def _coerce_confidence(value: object) -> float:
    try:
        val = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, val))


def _usage_dict(prompt_tokens: int, completion_tokens: int, total_tokens: int) -> dict[str, int]:
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def _trim_justification(user_justification: str | None) -> tuple[str, list[str]]:
    guardrails: list[str] = []
    trimmed = (user_justification or "").strip()
    if len(trimmed) > MIN_JUSTIFICATION_LEN:
        trimmed = trimmed[:MIN_JUSTIFICATION_LEN]
        guardrails.append("justification_truncated")
    return trimmed, guardrails


def _deterministic_decision(
    *,
    clue_text: str,
    expected_response: str,
    user_response: str,
    fuzzy_correct: bool,
    user_justification: str | None,
) -> AppealDecision:
    _, guardrails = _trim_justification(user_justification)

    if fuzzy_correct:
        guardrails.append("already_correct_attempt")
        return AppealDecision(
            overturn=False,
            final_correct=True,
            reason_code="already_correct",
            reason="Original grading already marked this response correct.",
            confidence=0.99,
            guardrail_flags=guardrails,
            model="deterministic_fallback",
            prompt_version=PROMPT_VERSION,
            usage=_usage_dict(0, 0, 0),
            raw_output={"source": "deterministic"},
        )

    user_norm = normalize(user_response)
    if not user_norm:
        return AppealDecision(
            overturn=False,
            final_correct=False,
            reason_code="empty_response",
            reason="Blank responses are not eligible for appeal.",
            confidence=0.99,
            guardrail_flags=guardrails,
            model="deterministic_fallback",
            prompt_version=PROMPT_VERSION,
            usage=_usage_dict(0, 0, 0),
            raw_output={"source": "deterministic"},
        )

    for alt in extract_alternates(expected_response):
        if user_norm == normalize(alt):
            return AppealDecision(
                overturn=True,
                final_correct=True,
                reason_code="exact_match",
                reason="Appeal accepted: response matches an expected answer form.",
                confidence=0.99,
                guardrail_flags=guardrails,
                model="deterministic_fallback",
                prompt_version=PROMPT_VERSION,
                usage=_usage_dict(0, 0, 0),
                raw_output={"source": "deterministic"},
            )

    if _looks_like_person_clue(clue_text):
        user_last = _single_token(user_response)
        if user_last:
            for alt in extract_alternates(expected_response):
                expected_last = _expected_last_name(alt)
                if expected_last and user_last == expected_last:
                    return AppealDecision(
                        overturn=True,
                        final_correct=True,
                        reason_code="last_name_match",
                        reason="Appeal accepted: last-name-only response is accepted for person clues.",
                        confidence=0.91,
                        guardrail_flags=guardrails,
                        model="deterministic_fallback",
                        prompt_version=PROMPT_VERSION,
                        usage=_usage_dict(0, 0, 0),
                        raw_output={"source": "deterministic"},
                    )

    expected_norm = normalize(re.sub(r"\(.*?\)", "", expected_response))
    if len(user_norm.split()) == 1 and len(expected_norm.split()) > 1:
        return AppealDecision(
            overturn=False,
            final_correct=False,
            reason_code="insufficient_specificity",
            reason="Appeal denied: response is less specific than the expected answer.",
            confidence=0.95,
            guardrail_flags=guardrails,
            model="deterministic_fallback",
            prompt_version=PROMPT_VERSION,
            usage=_usage_dict(0, 0, 0),
            raw_output={"source": "deterministic"},
        )

    scores = []
    for alt in extract_alternates(expected_response):
        alt_norm = normalize(alt)
        scores.append(fuzz.ratio(user_norm, alt_norm))
        scores.append(fuzz.token_sort_ratio(user_norm, alt_norm))
    if (max(scores) if scores else 0) >= FUZZ_THRESHOLD:
        return AppealDecision(
            overturn=True,
            final_correct=True,
            reason_code="strong_fuzzy_match",
            reason="Appeal accepted based on strong textual similarity.",
            confidence=HIGH_CONFIDENCE_THRESHOLD,
            guardrail_flags=guardrails,
            model="deterministic_fallback",
            prompt_version=PROMPT_VERSION,
            usage=_usage_dict(0, 0, 0),
            raw_output={"source": "deterministic"},
        )

    return AppealDecision(
        overturn=False,
        final_correct=False,
        reason_code="no_match",
        reason="Appeal denied: response does not meet matching policy.",
        confidence=0.94,
        guardrail_flags=guardrails,
        model="deterministic_fallback",
        prompt_version=PROMPT_VERSION,
        usage=_usage_dict(0, 0, 0),
        raw_output={"source": "deterministic"},
    )


def _schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "overturn": {"type": "boolean"},
            "final_correct": {"type": "boolean"},
            "reason_code": {"type": "string", "enum": sorted(ALLOWED_REASON_CODES)},
            "match_type": {"type": "string", "enum": sorted(ALLOWED_MATCH_TYPES)},
            "same_entity_likelihood": {"type": "number"},
            "reason": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": [
            "overturn",
            "final_correct",
            "reason_code",
            "match_type",
            "same_entity_likelihood",
            "reason",
            "confidence",
        ],
        "additionalProperties": False,
    }


def _normalize_llm_payload(
    payload: dict[str, object],
    *,
    model: str,
    response_id: str | None,
    usage: dict[str, int],
) -> AppealDecision:
    confidence = _coerce_confidence(payload.get("confidence"))
    same_entity_likelihood = _coerce_confidence(payload.get("same_entity_likelihood"))
    reason_code = str(payload.get("reason_code", "no_match"))
    if reason_code not in ALLOWED_REASON_CODES:
        reason_code = "no_match"
    match_type = str(payload.get("match_type", "no_match"))
    if match_type not in ALLOWED_MATCH_TYPES:
        match_type = "no_match"

    reason_text = str(payload.get("reason", "Appeal judged."))[:MAX_REASON_CHARS]
    guardrails: list[str] = []
    overturn = bool(payload.get("overturn"))
    final_correct = bool(payload.get("final_correct"))
    accept_candidate = overturn or final_correct
    overturn = accept_candidate
    if accept_candidate and bool(payload.get("overturn")) != bool(payload.get("final_correct")):
        guardrails.append("normalized_accept_flag_consistency")

    if overturn and confidence < HIGH_CONFIDENCE_THRESHOLD:
        guardrails.append("low_confidence_no_overturn")
        overturn = False
        final_correct = False
        reason_code = "no_match"
        logger.warning(
            "Appeal judge guardrail applied: low_confidence_no_overturn (confidence=%.3f)",
            confidence,
        )
    if overturn and same_entity_likelihood < SAME_ENTITY_THRESHOLD:
        guardrails.append("low_same_entity_no_overturn")
        overturn = False
        final_correct = False
        reason_code = "no_match"
        logger.warning(
            "Appeal judge guardrail applied: low_same_entity_no_overturn (same_entity_likelihood=%.3f)",
            same_entity_likelihood,
        )

    final_correct = overturn
    if overturn:
        if reason_code not in ACCEPT_REASON_CODES:
            reason_code = {
                "exact": "exact_match",
                "alias": "semantic_equivalence",
                "last_name": "last_name_match",
                "minor_typo": "minor_typo_match",
            }.get(match_type, "semantic_equivalence")
            guardrails.append("normalized_accept_reason_code")
    elif reason_code not in REJECT_REASON_CODES:
        reason_code = "no_match"
        guardrails.append("normalized_reject_reason_code")

    if (
        "low_confidence_no_overturn" in guardrails
        or "low_same_entity_no_overturn" in guardrails
        or "normalized_reject_reason_code" in guardrails
    ):
        reason_text = "Appeal denied: response does not meet matching policy."
    elif "normalized_accept_reason_code" in guardrails:
        reason_text = "Appeal accepted: response matches the same intended entity."

    return AppealDecision(
        overturn=overturn,
        final_correct=final_correct,
        reason_code=reason_code,
        reason=reason_text,
        confidence=confidence,
        guardrail_flags=guardrails,
        model=model,
        prompt_version=PROMPT_VERSION,
        usage=usage,
        raw_output={
            "provider": "openai",
            "response_id": response_id,
            "parsed": payload,
            "match_type": match_type,
            "same_entity_likelihood": same_entity_likelihood,
        },
    )


def run_appeal_judge(
    agent_input: AppealJudgeInput,
    *,
    runner: OpenAIJsonSchemaRunner | None = None,
) -> AppealDecision:
    runner = runner or _default_runner()
    request = JsonSchemaRequest(
        system_prompt=build_system_prompt(),
        user_prompt=build_user_prompt(agent_input),
        schema_name="appeal_decision",
        schema=_schema(),
    )
    response = runner.run_json_schema(request)
    return _normalize_llm_payload(
        response.payload,
        model=response.model,
        response_id=response.response_id,
        usage=_usage_dict(
            response.usage.prompt_tokens,
            response.usage.completion_tokens,
            response.usage.total_tokens,
        ),
    )


def judge_appeal(
    *,
    clue_text: str,
    expected_response: str,
    user_response: str,
    fuzzy_correct: bool,
    user_justification: str | None,
    runner: OpenAIJsonSchemaRunner | None = None,
) -> AppealDecision:
    trimmed_justification, _ = _trim_justification(user_justification)
    if fuzzy_correct or not normalize(user_response):
        return _deterministic_decision(
            clue_text=clue_text,
            expected_response=expected_response,
            user_response=user_response,
            fuzzy_correct=fuzzy_correct,
            user_justification=trimmed_justification,
        )

    try:
        return run_appeal_judge(
            AppealJudgeInput(
                clue_text=clue_text,
                expected_response=expected_response,
                user_response=user_response,
                user_justification=trimmed_justification,
            ),
            runner=runner,
        )
    except Exception as exc:
        logger.exception("Appeal judge LLM failed; using deterministic fallback")
        fallback = _deterministic_decision(
            clue_text=clue_text,
            expected_response=expected_response,
            user_response=user_response,
            fuzzy_correct=fuzzy_correct,
            user_justification=trimmed_justification,
        )
        fallback.guardrail_flags.append("llm_fallback")
        fallback.guardrail_flags.append(type(exc).__name__)
        fallback.raw_output = {
            "source": "deterministic",
            "llm_error_type": type(exc).__name__,
            "llm_error_message": str(exc),
        }
        return fallback


def judge_appeal_llm_only(
    *,
    clue_text: str,
    expected_response: str,
    user_response: str,
    user_justification: str | None,
    runner: OpenAIJsonSchemaRunner | None = None,
) -> tuple[AppealDecision | None, LLMJudgeFailure | None]:
    trimmed_justification, _ = _trim_justification(user_justification)
    try:
        decision = run_appeal_judge(
            AppealJudgeInput(
                clue_text=clue_text,
                expected_response=expected_response,
                user_response=user_response,
                user_justification=trimmed_justification,
            ),
            runner=runner,
        )
        return decision, None
    except Exception as exc:
        logger.warning("Appeal judge LLM-only path failed: %s", type(exc).__name__)
        return None, LLMJudgeFailure(
            error_type=type(exc).__name__,
            error_message=str(exc),
        )


def judge_appeal_llm_only_observed(
    cur,
    *,
    trace_id: str,
    run_type: str,
    clue_id: int,
    clue_text: str,
    expected_response: str,
    user_response: str,
    user_justification: str | None,
    runner: OpenAIJsonSchemaRunner | None = None,
) -> ObservedAppealJudgeResult:
    runner = runner or _default_runner()
    run_id = create_agent_run(
        cur,
        trace_id=trace_id,
        run_type=run_type,
        agent_name=AGENT_NAME,
        agent_version=AGENT_VERSION,
        policy_version=POLICY_VERSION,
        model=runner.resolve_model(),
        prompt_version=PROMPT_VERSION,
        input_payload={
            "clue_id": clue_id,
            "clue_text": clue_text,
            "expected_response": expected_response,
            "user_response": user_response,
            "user_justification": user_justification,
        },
    )
    log_agent_event(
        cur,
        agent_run_id=run_id,
        event_type="agent_invoked",
        level="info",
        message="Appeal judge invoked after deterministic defer.",
        payload={"clue_id": clue_id},
    )

    llm_start = perf_counter()
    decision, failure = judge_appeal_llm_only(
        clue_text=clue_text,
        expected_response=expected_response,
        user_response=user_response,
        user_justification=user_justification,
        runner=runner,
    )
    latency_ms = int((perf_counter() - llm_start) * 1000)

    if decision is not None:
        add_agent_artifact(
            cur,
            agent_run_id=run_id,
            artifact_type="decision",
            content={
                "final_correct": decision.final_correct,
                "reason_code": decision.reason_code,
                "reason": decision.reason,
                "confidence": decision.confidence,
            },
        )
        add_agent_artifact(
            cur,
            agent_run_id=run_id,
            artifact_type="model_output",
            content=decision.raw_output,
        )
        finish_agent_run(
            cur,
            agent_run_id=run_id,
            status="completed",
            output_payload={
                "final_correct": decision.final_correct,
                "reason_code": decision.reason_code,
                "reason": decision.reason,
                "confidence": decision.confidence,
            },
            guardrail_flags=decision.guardrail_flags,
            prompt_tokens=decision.usage.get("prompt_tokens"),
            completion_tokens=decision.usage.get("completion_tokens"),
            total_tokens=decision.usage.get("total_tokens"),
            latency_ms=latency_ms,
        )
        return ObservedAppealJudgeResult(
            run_id=run_id,
            latency_ms=latency_ms,
            decision=decision,
            failure=None,
        )

    log_agent_event(
        cur,
        agent_run_id=run_id,
        event_type="agent_failed",
        level="warn",
        message="Appeal judge LLM call failed.",
        payload={
            "error_type": failure.error_type if failure else "UnknownError",
            "error_message": failure.error_message if failure else "",
        },
    )
    finish_agent_run(
        cur,
        agent_run_id=run_id,
        status="failed",
        output_payload={
            "final_correct": False,
            "reason_code": "llm_unavailable_auto_reject",
            "reason": (
                f"LLM judge failed ({failure.error_type if failure else 'UnknownError'}); "
                "auto-rejected by caller policy."
            ),
        },
        guardrail_flags=[
            "llm_unavailable_auto_reject",
            failure.error_type if failure else "UnknownError",
        ],
        error_message=failure.error_message if failure else "LLM judge failed",
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        latency_ms=latency_ms,
    )
    return ObservedAppealJudgeResult(
        run_id=run_id,
        latency_ms=latency_ms,
        decision=None,
        failure=failure,
    )
