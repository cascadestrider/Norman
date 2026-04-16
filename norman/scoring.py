from norman.config import KEYWORDS


def score_text(text: str) -> tuple[list[str], int]:
    """Score text against the keyword table.

    Returns (matched_keywords, total_score).
    Each keyword counts up to 3 occurrences. Total capped at 100.
    """
    text_lower = text.lower()
    found = []
    total = 0
    for keyword, weight in KEYWORDS.items():
        count = text_lower.count(keyword)
        if count > 0:
            found.append(keyword)
            total += weight * min(count, 3)
    return found, min(total, 100)
