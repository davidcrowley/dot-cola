from __future__ import annotations

import re


_SPACE_RE = re.compile(r"\s+")


def normalize_text(text: str, *, normalize_ocr_confusions: bool = False) -> str:
    normalized = text.strip().lower()
    normalized = _SPACE_RE.sub(" ", normalized)

    if normalize_ocr_confusions:
        normalized = _normalize_careful_confusions(normalized)

    return normalized


def _normalize_careful_confusions(text: str) -> str:
    """Normalize common OCR confusions inside alphanumeric identifiers only."""
    chars = list(text)
    for index, char in enumerate(chars):
        prev_char = chars[index - 1] if index > 0 else ""
        next_char = chars[index + 1] if index + 1 < len(chars) else ""
        near_digit = prev_char.isdigit() or next_char.isdigit()

        if near_digit and char == "o":
            chars[index] = "0"
        elif near_digit and char in {"i", "l"}:
            chars[index] = "1"
    return "".join(chars)

