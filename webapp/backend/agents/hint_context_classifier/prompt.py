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
        "4) Do not mark true just because a fact could theoretically change over time.\n"
        "5) Do not mark true for stable institutional facts, geography, definitions, abbreviations, "
        "or ordinary subject-matter knowledge.\n"
        "6) Mark true when the clue itself contains a real time anchor such as current, currently, "
        "now, at the time, then, this year, today, as of, incumbent, defending champion, or reigning, "
        "and that anchor changes the fair answer.\n"
        "7) If present-day knowledge would probably produce the same answer, return false.\n"
        "8) Precision matters more than recall, so return false when uncertain.\n\n"
        "Examples:\n"
        "- Clue: This current Fed chairman is the author of a book on the Great Depression "
        "| Expected: Bernanke => true\n"
        "- Clue: There are 12 Federal Reserve Banks; the one for the 12th district is based in this city "
        "| Expected: San Francisco => false\n"
        "- Clue: The Fed controls how much money is out there partly by buying or selling T-bills, "
        "\"T\" for this cabinet department | Expected: Treasury => false\n\n"
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
