from __future__ import annotations

import logging
from time import perf_counter

try:
    from ...agent_observability import (
        add_agent_artifact,
        create_agent_run,
        finish_agent_run,
        log_agent_event,
    )
except ImportError:
    from agent_observability import add_agent_artifact, create_agent_run, finish_agent_run, log_agent_event

from ..runtime import AgentSpec, JsonSchemaRequest, OpenAIJsonSchemaRunner
from .prompt import build_system_prompt, build_user_prompt
from .types import (
    HintContextClassification,
    HintContextClassifierInput,
    LLMHintContextFailure,
    ObservedHintContextClassifierResult,
)

AGENT_NAME = "hint_context_classifier"
AGENT_VERSION = "v1"
POLICY_VERSION = "hint_context_policy_v1"
PROMPT_VERSION = "hint_context_prompt_v1"

DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_TIMEOUT_MS = 7000
MAX_REASON_CHARS = 600
TEMPORAL_ANCHORS = (
    "current",
    "currently",
    "now",
    "at the time",
    "then",
    "this year",
    "this season",
    "today",
    "as of",
    "incumbent",
    "defending champion",
    "reigning",
)
ALLOWED_REASON_CODES = {
    "current_officeholder",
    "current_titleholder",
    "relative_time_reference",
    "broadcast_time_reference",
    "time_bounded_status",
    "not_point_in_time",
}
POSITIVE_REASON_CODES = ALLOWED_REASON_CODES - {"not_point_in_time"}
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
        model_env_var="HINT_CONTEXT_MODEL",
        timeout_env_var="HINT_CONTEXT_TIMEOUT_MS",
        default_timeout_ms=DEFAULT_TIMEOUT_MS,
    )


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


def _deterministic_not_point_in_time(reason: str) -> HintContextClassification:
    return HintContextClassification(
        is_point_in_time=False,
        reason_code="not_point_in_time",
        reason=reason,
        confidence=0.99,
        guardrail_flags=["no_temporal_anchor"],
        model="deterministic_fallback",
        prompt_version=PROMPT_VERSION,
        usage=_usage_dict(0, 0, 0),
        raw_output={"source": "deterministic"},
    )


def _has_temporal_anchor(clue_text: str) -> bool:
    lowered = f" {clue_text.lower()} "
    return any(f" {anchor} " in lowered for anchor in TEMPORAL_ANCHORS)


def _schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "is_point_in_time": {"type": "boolean"},
            "reason_code": {"type": "string", "enum": sorted(ALLOWED_REASON_CODES)},
            "reason": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": ["is_point_in_time", "reason_code", "reason", "confidence"],
        "additionalProperties": False,
    }


def _normalize_llm_payload(
    payload: dict[str, object],
    *,
    model: str,
    response_id: str | None,
    usage: dict[str, int],
) -> HintContextClassification:
    confidence = _coerce_confidence(payload.get("confidence"))
    is_point_in_time = bool(payload.get("is_point_in_time"))
    reason_code = str(payload.get("reason_code", "not_point_in_time"))
    if reason_code not in ALLOWED_REASON_CODES:
        reason_code = "not_point_in_time"
    reason_text = str(payload.get("reason", "Hint context classified."))[:MAX_REASON_CHARS]

    guardrails: list[str] = []
    if is_point_in_time and reason_code == "not_point_in_time":
        reason_code = "relative_time_reference"
        guardrails.append("normalized_positive_reason_code")
    elif (not is_point_in_time) and reason_code in POSITIVE_REASON_CODES:
        reason_code = "not_point_in_time"
        guardrails.append("normalized_negative_reason_code")

    return HintContextClassification(
        is_point_in_time=is_point_in_time,
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
        },
    )


def run_hint_context_classifier(
    agent_input: HintContextClassifierInput,
    *,
    runner: OpenAIJsonSchemaRunner | None = None,
) -> HintContextClassification:
    if not _has_temporal_anchor(agent_input.clue_text):
        return _deterministic_not_point_in_time(
            "Clue lacks an explicit temporal anchor, so it is treated as not point-in-time-sensitive."
        )

    runner = runner or _default_runner()
    request = JsonSchemaRequest(
        system_prompt=build_system_prompt(),
        user_prompt=build_user_prompt(agent_input),
        schema_name="hint_context_classification",
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


def classify_hint_context_llm_only(
    *,
    clue_text: str,
    expected_response: str,
    category: str,
    air_date: str,
    runner: OpenAIJsonSchemaRunner | None = None,
) -> tuple[HintContextClassification | None, LLMHintContextFailure | None]:
    try:
        classification = run_hint_context_classifier(
            HintContextClassifierInput(
                clue_text=clue_text,
                expected_response=expected_response,
                category=category,
                air_date=air_date,
            ),
            runner=runner,
        )
        return classification, None
    except Exception as exc:
        logger.warning("Hint context classifier failed: %s", type(exc).__name__)
        return None, LLMHintContextFailure(
            error_type=type(exc).__name__,
            error_message=str(exc),
        )


def classify_hint_context_llm_only_observed(
    cur,
    *,
    trace_id: str,
    run_type: str,
    clue_id: int,
    clue_text: str,
    expected_response: str,
    category: str,
    air_date: str,
    runner: OpenAIJsonSchemaRunner | None = None,
) -> ObservedHintContextClassifierResult:
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
            "category": category,
            "air_date": air_date,
        },
    )
    log_agent_event(
        cur,
        agent_run_id=run_id,
        event_type="agent_invoked",
        level="info",
        message="Hint context classifier invoked for clue cache fill.",
        payload={"clue_id": clue_id},
    )

    llm_start = perf_counter()
    classification, failure = classify_hint_context_llm_only(
        clue_text=clue_text,
        expected_response=expected_response,
        category=category,
        air_date=air_date,
        runner=runner,
    )
    latency_ms = int((perf_counter() - llm_start) * 1000)

    if classification is not None:
        add_agent_artifact(
            cur,
            agent_run_id=run_id,
            artifact_type="classification",
            content={
                "is_point_in_time": classification.is_point_in_time,
                "reason_code": classification.reason_code,
                "reason": classification.reason,
                "confidence": classification.confidence,
            },
        )
        add_agent_artifact(
            cur,
            agent_run_id=run_id,
            artifact_type="model_output",
            content=classification.raw_output,
        )
        finish_agent_run(
            cur,
            agent_run_id=run_id,
            status="completed",
            output_payload={
                "is_point_in_time": classification.is_point_in_time,
                "reason_code": classification.reason_code,
                "reason": classification.reason,
                "confidence": classification.confidence,
            },
            guardrail_flags=classification.guardrail_flags,
            prompt_tokens=classification.usage.get("prompt_tokens"),
            completion_tokens=classification.usage.get("completion_tokens"),
            total_tokens=classification.usage.get("total_tokens"),
            latency_ms=latency_ms,
        )
        return ObservedHintContextClassifierResult(
            run_id=run_id,
            latency_ms=latency_ms,
            classification=classification,
            failure=None,
        )

    log_agent_event(
        cur,
        agent_run_id=run_id,
        event_type="agent_failed",
        level="warn",
        message="Hint context classifier LLM call failed.",
        payload={
            "error_type": failure.error_type if failure else "UnknownError",
            "error_message": failure.error_message if failure else "",
        },
    )
    finish_agent_run(
        cur,
        agent_run_id=run_id,
        status="failed",
        output_payload={"is_point_in_time": False, "reason_code": "not_point_in_time"},
        guardrail_flags=[failure.error_type if failure else "UnknownError"],
        error_message=failure.error_message if failure else "Hint context classifier failed",
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        latency_ms=latency_ms,
    )
    return ObservedHintContextClassifierResult(
        run_id=run_id,
        latency_ms=latency_ms,
        classification=None,
        failure=failure,
    )
