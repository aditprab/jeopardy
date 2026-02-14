import re
from thefuzz import fuzz

STRIP_PREFIXES = re.compile(
    r"^(what|who|where|when)\s+(is|are|was|were)\s+",
    re.IGNORECASE,
)
STRIP_ARTICLES = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)
PAREN_ALT = re.compile(r"\((?:or\s+)?(.+?)\)")
PUNCTUATION = re.compile(r"[^\w\s]")
MULTI_SPACE = re.compile(r"\s+")

THRESHOLD = 80


def normalize(text: str) -> str:
    text = STRIP_PREFIXES.sub("", text)
    text = STRIP_ARTICLES.sub("", text)
    text = PUNCTUATION.sub("", text)
    text = MULTI_SPACE.sub(" ", text).strip().lower()
    return text


def extract_alternates(expected: str) -> list[str]:
    """Extract alternate answers from parentheticals like 'Nihon (or Nippon)'."""
    alts = PAREN_ALT.findall(expected)
    base = PAREN_ALT.sub("", expected).strip()
    results = [base]
    results.extend(alts)
    return results


def check_answer(user_response: str, expected: str) -> tuple[bool, str]:
    """Returns (is_correct, expected_display)."""
    user_norm = normalize(user_response)
    alternates = extract_alternates(expected)

    for alt in alternates:
        alt_norm = normalize(alt)
        ratio = fuzz.ratio(user_norm, alt_norm)
        token_ratio = fuzz.token_sort_ratio(user_norm, alt_norm)
        if ratio >= THRESHOLD or token_ratio >= THRESHOLD:
            return True, expected

    return False, expected
