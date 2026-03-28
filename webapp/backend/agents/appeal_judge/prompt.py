from __future__ import annotations

from .types import AppealJudgeInput


def build_system_prompt() -> str:
    return (
        "You are a strict Jeopardy answer-appeal judge. "
        "Decide if the user likely knew the same intended entity. "
        "Return only valid JSON matching the schema."
    )


def build_user_prompt(agent_input: AppealJudgeInput) -> str:
    return (
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
        f"Clue: {agent_input.clue_text}\n"
        f"Expected: {agent_input.expected_response}\n"
        f"User response: {agent_input.user_response}\n"
        f"User appeal note: {agent_input.user_justification or '(none)'}"
    )
