from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - dependency may be installed after deploy
    OpenAI = None  # type: ignore[assignment]
from thefuzz import fuzz

try:
    from .answer import extract_alternates, normalize
except ImportError:
    from answer import extract_alternates, normalize

AGENT_NAME = "appeal_judge"
AGENT_VERSION = "v4"
POLICY_VERSION = "appeal_policy_v4"
PROMPT_VERSION = "appeal_prompt_v2"

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

_client: OpenAI | None = None
logger = logging.getLogger(__name__)


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


@dataclass
class LLMJudgeFailure:
    error_type: str
    error_message: str


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


def _usage_dict(resp: Any) -> dict[str, int]:
    usage = getattr(resp, "usage", None)
    if usage is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    total_tokens = int(getattr(usage, "total_tokens", input_tokens + output_tokens) or 0)
    return {
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _coerce_confidence(value: Any) -> float:
    try:
        val = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, val))


def _deterministic_decision(
    *,
    clue_text: str,
    expected_response: str,
    user_response: str,
    fuzzy_correct: bool,
    user_justification: str | None,
) -> AppealDecision:
    guardrails: list[str] = []

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
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            raw_output={"source": "deterministic"},
        )

    if user_justification and len(user_justification) > MIN_JUSTIFICATION_LEN:
        guardrails.append("justification_truncated")
        user_justification = user_justification[:MIN_JUSTIFICATION_LEN]

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
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
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
                usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
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
                        usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
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
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
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
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
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
        usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        raw_output={"source": "deterministic"},
    )


def _get_client() -> OpenAI | None:
    global _client
    if OpenAI is None:
        logger.warning("Appeal judge fallback: openai package not installed")
        return None
    if _client is not None:
        return _client
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("Appeal judge fallback: OPENAI_API_KEY not configured")
        return None
    timeout_ms = int(os.getenv("JUDGE_TIMEOUT_MS", str(DEFAULT_TIMEOUT_MS)))
    _client = OpenAI(api_key=api_key, timeout=timeout_ms / 1000.0)
    logger.info("Appeal judge OpenAI client initialized (timeout_ms=%s)", timeout_ms)
    return _client


def _llm_decision(
    *,
    clue_text: str,
    expected_response: str,
    user_response: str,
    user_justification: str,
) -> AppealDecision:
    client = _get_client()
    if client is None:
        raise RuntimeError("OPENAI_API_KEY not configured")

    model = os.getenv("JUDGE_MODEL", DEFAULT_MODEL)
    logger.info("Appeal judge LLM request started (model=%s)", model)
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You are a strict Jeopardy answer-appeal judge. "
                            "Decide if the user likely knew the same intended entity. "
                            "Return only valid JSON matching the schema."
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Policy:\n"
                            "1) Last-name-only is usually acceptable for person clues.\n"
                            "2) Minor typos should be accepted only when they clearly indicate the same entity.\n"
                            "3) Deny when the response could plausibly indicate a different valid entity.\n"
                            "4) Subset-only responses for non-person entities should be denied.\n"
                            "5) Allow clear aliases and equivalent forms.\n"
                            "6) Be conservative when uncertain.\n\n"
                            "Examples:\n"
                            "- Expected: Warren Buffett | User: Buffet => Accept (minor_typo)\n"
                            "- Expected: Stephen Hawking | User: Hawkins => Accept (minor_typo)\n"
                            "- Expected: Marlon Brando | User: Brendan => Deny (no_match)\n\n"
                            f"Clue: {clue_text}\n"
                            f"Expected: {expected_response}\n"
                            f"User response: {user_response}\n"
                            f"User appeal note: {user_justification or '(none)'}"
                        ),
                    }
                ],
            },
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "appeal_decision",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "overturn": {"type": "boolean"},
                        "final_correct": {"type": "boolean"},
                        "reason_code": {
                            "type": "string",
                            "enum": sorted(ALLOWED_REASON_CODES),
                        },
                        "match_type": {
                            "type": "string",
                            "enum": sorted(ALLOWED_MATCH_TYPES),
                        },
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
                },
            }
        },
    )
    raw_text = getattr(response, "output_text", "") or ""
    payload = json.loads(raw_text)
    logger.info("Appeal judge LLM request completed (model=%s)", model)
    confidence = _coerce_confidence(payload.get("confidence"))
    same_entity_likelihood = _coerce_confidence(payload.get("same_entity_likelihood"))
    reason_code = payload.get("reason_code", "no_match")
    if reason_code not in ALLOWED_REASON_CODES:
        reason_code = "no_match"
    match_type = payload.get("match_type", "no_match")
    if match_type not in ALLOWED_MATCH_TYPES:
        match_type = "no_match"

    reason_text = str(payload.get("reason", "Appeal judged."))[:MAX_REASON_CHARS]

    guardrails: list[str] = []
    overturn = bool(payload.get("overturn"))
    final_correct = bool(payload.get("final_correct"))
    # If either flag says "accept", treat as a positive candidate before guardrails.
    accept_candidate = overturn or final_correct
    overturn = accept_candidate
    if accept_candidate and not bool(payload.get("overturn")) == bool(payload.get("final_correct")):
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
    # Normalize for storage consistency: in appeal outcomes, overturn implies correct.
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
        usage=_usage_dict(response),
        raw_output={
            "provider": "openai",
            "response_id": getattr(response, "id", None),
            "parsed": payload,
            "match_type": match_type,
            "same_entity_likelihood": same_entity_likelihood,
        },
    )


def judge_appeal(
    *,
    clue_text: str,
    expected_response: str,
    user_response: str,
    fuzzy_correct: bool,
    user_justification: str | None,
) -> AppealDecision:
    trimmed_justification = (user_justification or "").strip()
    if len(trimmed_justification) > MIN_JUSTIFICATION_LEN:
        trimmed_justification = trimmed_justification[:MIN_JUSTIFICATION_LEN]

    # Hard pre-checks are deterministic to avoid needless model calls.
    if fuzzy_correct or not normalize(user_response):
        return _deterministic_decision(
            clue_text=clue_text,
            expected_response=expected_response,
            user_response=user_response,
            fuzzy_correct=fuzzy_correct,
            user_justification=trimmed_justification,
        )

    try:
        return _llm_decision(
            clue_text=clue_text,
            expected_response=expected_response,
            user_response=user_response,
            user_justification=trimmed_justification,
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
) -> tuple[AppealDecision | None, LLMJudgeFailure | None]:
    trimmed_justification = (user_justification or "").strip()
    if len(trimmed_justification) > MIN_JUSTIFICATION_LEN:
        trimmed_justification = trimmed_justification[:MIN_JUSTIFICATION_LEN]

    try:
        decision = _llm_decision(
            clue_text=clue_text,
            expected_response=expected_response,
            user_response=user_response,
            user_justification=trimmed_justification,
        )
        return decision, None
    except Exception as exc:
        logger.warning("Appeal judge LLM-only path failed: %s", type(exc).__name__)
        return None, LLMJudgeFailure(
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
