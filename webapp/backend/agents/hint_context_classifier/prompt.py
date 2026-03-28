from __future__ import annotations

from .types import HintContextClassifierInput


def build_system_prompt() -> str:
    return (
        "You classify Jeopardy clues for user-facing hint context. "
        "Use only the supplied clue text, expected answer, category, and air date. "
        "Be conservative and optimize for precision. "
        "Return only valid JSON matching the schema."
    )


def build_user_prompt(agent_input: HintContextClassifierInput) -> str:
    return (
        "Task:\n"
        "Decide whether a reasonable player could answer incorrectly by using present-day knowledge "
        "instead of the clue's original air date.\n\n"
        "Rules:\n"
        "1) Use only the supplied clue text, expected answer, category, and air date.\n"
        "2) Do not rely on current real-world facts beyond what the clue itself implies.\n"
        "3) Mark true only when the air date materially changes what a fair answer should be.\n"
        "4) Precision matters more than recall, so return false when uncertain.\n\n"
        "Reason code guide:\n"
        "- current_officeholder\n"
        "- current_titleholder\n"
        "- relative_time_reference\n"
        "- broadcast_time_reference\n"
        "- time_bounded_status\n"
        "- not_point_in_time\n\n"
        f"Category: {agent_input.category}\n"
        f"Air date: {agent_input.air_date}\n"
        f"Clue: {agent_input.clue_text}\n"
        f"Expected answer: {agent_input.expected_response}"
    )
