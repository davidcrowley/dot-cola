from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

from rapidfuzz import fuzz

from app.matching.normalizer import normalize_text
from app.models import BBox, MatchResult, OCRTextBox


@dataclass(frozen=True)
class MatchCandidate:
    text: str
    ocr_confidence: float | None
    bbox: BBox | None
    source: str
    line_count: int


@dataclass(frozen=True)
class MatchPolicy:
    field: str
    mode: Literal["loose", "exactish", "contains", "warning"] = "exactish"
    max_lines: int | None = 1
    punctuation_insensitive: bool = True
    normalize_ocr_confusions: bool = True


_PUNCTUATION_RE = re.compile(r"[^\w\s]+", re.ASCII)
_TEXT_SEPARATOR_RE = re.compile(r"\s*[-|:;•·–—]+\s*")
_ALCOHOL_TOKEN_RE = re.compile(
    r"alc(?:ohol)?|wt|weight|vol(?:ume)?|by|\d+(?:\.\d+)?",
    re.IGNORECASE,
)
_GOVERNMENT_WARNING_ANCHOR = "government warning"
_GOVERNMENT_WARNING_CHUNKS = [
    "according to the surgeon general",
    "women should not drink",
    "alcoholic beverages",
    "during pregnancy",
    "risk of birth defects",
    "consumption of alcoholic beverages",
    "impairs your ability",
    "drive a car",
    "operate machinery",
    "may cause health problems",
    "drink",
    "alcoholic",
    "machinery",
]
_WARNING_END_PHRASES = [
    "may cause health problems",
    "health problems",
    "operate machinery",
    "machinery",
    "drive a car",
    "impairs your ability",
    "consumption of alcoholic beverages",
    "birth defects",
    "risk of birth defects",
]
_WARNING_TERMINAL_PHRASES = [
    "may cause health problems",
    "health problems",
    "operate machinery",
    "machinery",
]


def match_targets(
    ocr_boxes: list[OCRTextBox],
    targets: list[str],
    match_threshold: int = 85,
    policies: list[MatchPolicy] | None = None,
) -> list[MatchResult]:
    candidates = build_candidates(ocr_boxes, targets=targets)
    target_policies = policies or [MatchPolicy(field=str(index)) for index, _ in enumerate(targets)]
    return [
        _match_one_target(target, policy, candidates, match_threshold)
        for target, policy in zip(targets, target_policies)
    ]


def build_candidates(
    ocr_boxes: list[OCRTextBox],
    *,
    targets: list[str] | None = None,
    max_group_size: int | None = None,
) -> list[MatchCandidate]:
    candidates: list[MatchCandidate] = [
        MatchCandidate(box.text, box.confidence, box.bbox, "single_box", 1) for box in ocr_boxes
    ]

    lines = _group_same_line_boxes(ocr_boxes)
    span_limit = max_group_size or _target_group_limit(targets or [])
    for line in lines:
        if len(line) > 1:
            candidates.append(_candidate_from_boxes(line, "line_group"))
        candidates.extend(_adjacent_candidates(line, max_group_size=span_limit))

    candidates.extend(_stacked_line_candidates(lines))
    candidates.extend(_cross_line_candidates(lines, max_group_size=span_limit))
    candidates.extend(_separator_split_candidates(candidates))

    if ocr_boxes:
        full_text = " ".join(box.text for box in _sort_reading_order(ocr_boxes))
        confidence = sum(box.confidence for box in ocr_boxes) / len(ocr_boxes)
        line_count = len(lines) if lines else 1
        candidates.append(MatchCandidate(full_text, confidence, None, "full_text", line_count))

    return _dedupe_candidates(candidates)


def _match_one_target(
    target: str,
    policy: MatchPolicy,
    candidates: list[MatchCandidate],
    match_threshold: int,
) -> MatchResult:
    best_candidate: MatchCandidate | None = None
    best_score = 0.0

    normalized_target = _normalize_for_policy(target, policy)
    for candidate in candidates:
        if policy.max_lines is not None and candidate.line_count > policy.max_lines:
            continue
        normalized_candidate = _normalize_for_policy(candidate.text, policy)
        score = _candidate_score(normalized_target, normalized_candidate, policy)
        if _is_better_candidate(score, normalized_candidate, best_score, best_candidate, policy):
            best_score = float(score)
            best_candidate = candidate

    found = best_candidate is not None and best_score >= match_threshold
    ocr_confidence = best_candidate.ocr_confidence if best_candidate else None
    combined_confidence = (
        ocr_confidence * (best_score / 100.0) if ocr_confidence is not None else None
    )

    matched_text = (
        _matched_text_for_policy(best_candidate.text, policy)
        if found and best_candidate
        else None
    )
    closest_text = (
        _matched_text_for_policy(best_candidate.text, policy)
        if not found and best_candidate
        else None
    )

    return MatchResult(
        target=target,
        found=found,
        matched_text=matched_text,
        closest_text=closest_text,
        score=round(best_score, 2),
        ocr_confidence=round(ocr_confidence, 4) if ocr_confidence is not None else None,
        combined_confidence=round(combined_confidence, 4)
        if combined_confidence is not None
        else None,
        bbox=best_candidate.bbox if best_candidate else None,
        candidate_source=best_candidate.source if best_candidate else "full_text",
    )


def _is_better_candidate(
    score: float,
    normalized_candidate: str,
    best_score: float,
    best_candidate: MatchCandidate | None,
    policy: MatchPolicy,
) -> bool:
    if score > best_score:
        return True
    if best_candidate is None or score < best_score:
        return False

    best_normalized = _normalize_for_policy(best_candidate.text, policy)
    if policy.mode == "warning":
        candidate_complete = _has_warning_terminal_health_clause(normalized_candidate)
        best_complete = _has_warning_terminal_health_clause(best_normalized)
        if candidate_complete != best_complete:
            return candidate_complete
        return len(normalized_candidate) < len(best_normalized)

    return len(normalized_candidate) < len(best_normalized)


def _candidate_score(
    normalized_target: str,
    normalized_candidate: str,
    policy: MatchPolicy,
) -> float:
    if not normalized_target or not normalized_candidate:
        return 0.0

    if normalized_target == normalized_candidate:
        return 100.0

    if _compact_text(normalized_target) == _compact_text(normalized_candidate):
        return 100.0

    if policy.mode == "warning":
        return _warning_score(normalized_target, normalized_candidate)

    if policy.field == "alcohol":
        alcohol_score = _alcohol_score(normalized_target, normalized_candidate)
        if alcohol_score is not None:
            return alcohol_score

    if policy.field == "address" and _contains_address_sequence(
        normalized_candidate,
        normalized_target,
    ):
        return 96.0

    if _contains_phrase(normalized_candidate, normalized_target):
        return 98.0

    if policy.mode == "loose":
        target_coverage = min(1.0, len(normalized_candidate) / len(normalized_target))
        return max(
            float(fuzz.ratio(normalized_target, normalized_candidate)),
            float(fuzz.partial_ratio(normalized_target, normalized_candidate)) * target_coverage,
            float(fuzz.token_set_ratio(normalized_target, normalized_candidate)) * target_coverage,
        )

    ratio_score = float(fuzz.ratio(normalized_target, normalized_candidate))
    partial_score = float(fuzz.partial_ratio(normalized_target, normalized_candidate))
    token_set_score = float(fuzz.token_set_ratio(normalized_target, normalized_candidate))

    length_ratio = _length_ratio(normalized_target, normalized_candidate)
    adjusted_partial = partial_score * length_ratio
    adjusted_token_set = token_set_score * length_ratio

    return max(ratio_score, adjusted_partial, adjusted_token_set)


def _normalize_for_policy(text: str, policy: MatchPolicy) -> str:
    if policy.field == "alcohol":
        alcohol_text = normalize_alcohol_text(text)
        if alcohol_text:
            return alcohol_text

    normalized = normalize_text(
        text,
        normalize_ocr_confusions=policy.normalize_ocr_confusions,
    )
    if policy.punctuation_insensitive:
        normalized = _PUNCTUATION_RE.sub(" ", normalized)
        normalized = normalize_text(normalized)
    return normalized


def _contains_phrase(normalized_candidate: str, normalized_target: str) -> bool:
    candidate = f" {normalized_candidate} "
    target = f" {normalized_target} "
    if target in candidate:
        return True

    compact_candidate = _compact_text(normalized_candidate)
    compact_target = _compact_text(normalized_target)
    return bool(compact_target) and compact_target in compact_candidate


def _compact_text(normalized_text: str) -> str:
    return normalized_text.replace(" ", "")


def _alcohol_score(normalized_target: str, normalized_candidate: str) -> float | None:
    if not looks_like_alcohol_declaration(normalized_target):
        return None
    if not looks_like_alcohol_declaration(normalized_candidate):
        return None

    target = normalize_alcohol_text(normalized_target)
    candidate = normalize_alcohol_text(normalized_candidate)
    if not target or not candidate:
        return None

    if target == candidate:
        return 100.0

    target_tokens = target.split()
    candidate_tokens = candidate.split()
    if _contains_token_window(candidate_tokens, target_tokens):
        return 100.0

    return None


def normalize_alcohol_text(text: str) -> str:
    tokens: list[str] = []
    for match in _ALCOHOL_TOKEN_RE.finditer(text.lower()):
        token = match.group(0).lower()
        if token == "by":
            continue
        if token.startswith("alc"):
            tokens.append("alc")
        elif token in {"wt", "weight"}:
            tokens.append("wt")
        elif token.startswith("vol"):
            tokens.append("vol")
        else:
            tokens.append(token)
    return " ".join(tokens)


def looks_like_alcohol_declaration(text: str) -> bool:
    tokens = normalize_alcohol_text(text).split()
    if not tokens:
        return False

    has_marker = any(token in {"alc", "wt", "vol"} for token in tokens)
    has_number = any(_is_numeric_token(token) for token in tokens)
    return has_marker and has_number


def _contains_token_window(candidate_tokens: list[str], target_tokens: list[str]) -> bool:
    if not target_tokens or len(target_tokens) > len(candidate_tokens):
        return False

    window_size = len(target_tokens)
    return any(
        candidate_tokens[start : start + window_size] == target_tokens
        for start in range(0, len(candidate_tokens) - window_size + 1)
    )


def _is_numeric_token(token: str) -> bool:
    return token.replace(".", "", 1).isdigit()


def _contains_address_sequence(normalized_candidate: str, normalized_target: str) -> bool:
    target = _address_compact_text(normalized_target)
    candidate = _address_compact_text(normalized_candidate)
    if len(target) < 8 or target not in candidate:
        return False

    words = [word for word in normalized_target.split() if len(word) > 2 or word.isdigit()]
    if not words:
        return False

    hits = sum(1 for word in words if _address_compact_text(word) in candidate)
    return hits / len(words) >= 0.8


def _address_compact_text(normalized_text: str) -> str:
    return _compact_text(normalized_text).replace("0", "o")


def _warning_score(normalized_target: str, normalized_candidate: str) -> float:
    if not _has_warning_anchor(normalized_candidate):
        return 0.0

    anchor_index = _warning_anchor_index(normalized_candidate)
    candidate_suffix = normalized_candidate[anchor_index:]
    target_coverage = min(1.0, len(candidate_suffix) / len(normalized_target))
    base_score = max(
        float(fuzz.ratio(normalized_target, candidate_suffix)),
        float(fuzz.partial_ratio(normalized_target, candidate_suffix)) * target_coverage,
        float(fuzz.token_set_ratio(normalized_target, candidate_suffix)) * target_coverage,
    )
    chunk_hits = sum(
        1 for chunk in _GOVERNMENT_WARNING_CHUNKS if _warning_chunk_present(candidate_suffix, chunk)
    )
    chunk_score = 70.0 + (30.0 * (chunk_hits / len(_GOVERNMENT_WARNING_CHUNKS)))
    if _has_noisy_warning_fragments(candidate_suffix):
        chunk_score = max(chunk_score, 86.0)
    return max(base_score, chunk_score)


def _matched_text_for_policy(text: str, policy: MatchPolicy) -> str:
    if policy.mode != "warning":
        return text
    return _trim_warning_match_text(text)


def _trim_warning_match_text(text: str) -> str:
    anchor_index = _warning_anchor_raw_index(text)
    trimmed = text[anchor_index:].lstrip()

    best_end = _first_available_phrase_end(trimmed, _WARNING_TERMINAL_PHRASES)
    if best_end <= 0:
        for phrase in _WARNING_END_PHRASES:
            best_end = max(best_end, _last_phrase_end(trimmed, phrase))

    if best_end <= 0:
        return trimmed

    return trimmed[:best_end].rstrip(" ,.;:")


def _warning_anchor_raw_index(text: str) -> int:
    anchor_match = re.search(r"\bgovern\w*[\W_]+warning\b", text, flags=re.IGNORECASE)
    if anchor_match:
        return anchor_match.start()

    lower_text = text.lower()
    truncated_index = lower_text.find("governm")
    if truncated_index >= 0:
        return truncated_index
    government_index = lower_text.find("government")
    if government_index >= 0:
        return government_index
    warning_match = re.search(r"\b(?:ent[\W_]+)?warning\b", text, flags=re.IGNORECASE)
    if warning_match:
        return warning_match.start()
    return 0


def _first_available_phrase_end(text: str, phrases: list[str]) -> int:
    for phrase in phrases:
        phrase_end = _first_phrase_end(text, phrase)
        if phrase_end > 0:
            return phrase_end
    return 0


def _first_phrase_end(text: str, phrase: str) -> int:
    words = [re.escape(word) for word in phrase.split()]
    pattern = r"\b" + r"[\W_]*".join(words) + r"\b"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match is None:
        return 0
    return match.end()


def _last_phrase_end(text: str, phrase: str) -> int:
    words = [re.escape(word) for word in phrase.split()]
    pattern = r"\b" + r"[\W_]*".join(words) + r"\b"
    matches = list(re.finditer(pattern, text, flags=re.IGNORECASE))
    if not matches:
        return 0
    return matches[-1].end()


def _has_warning_anchor(normalized_candidate: str) -> bool:
    return (
        _contains_phrase(normalized_candidate, _GOVERNMENT_WARNING_ANCHOR)
        or "governm" in normalized_candidate
        or _has_truncated_warning_anchor(normalized_candidate)
        or _has_fuzzy_warning_anchor(normalized_candidate)
    )


def _has_fuzzy_warning_anchor(normalized_candidate: str) -> bool:
    compact_candidate = _compact_text(normalized_candidate)
    compact_anchor = _compact_text(_GOVERNMENT_WARNING_ANCHOR)
    if len(compact_candidate) < len(compact_anchor) * 0.6:
        return False
    if "govern" not in compact_candidate and "warn" not in compact_candidate:
        return False
    return float(fuzz.partial_ratio(_GOVERNMENT_WARNING_ANCHOR, normalized_candidate)) >= 86.0


def _warning_anchor_index(normalized_candidate: str) -> int:
    exact_index = normalized_candidate.find(_GOVERNMENT_WARNING_ANCHOR)
    if exact_index >= 0:
        return exact_index
    truncated_index = normalized_candidate.find("governm")
    if truncated_index >= 0:
        return truncated_index
    warning_index = normalized_candidate.find("warning")
    if warning_index >= 0:
        return warning_index
    government_index = normalized_candidate.find("government")
    return max(government_index, 0)


def _warning_chunk_present(normalized_candidate: str, normalized_chunk: str) -> bool:
    if _contains_phrase(normalized_candidate, normalized_chunk):
        return True
    return float(fuzz.partial_ratio(normalized_chunk, normalized_candidate)) >= 92.0


def _has_noisy_warning_fragments(normalized_candidate: str) -> bool:
    if "governm" not in normalized_candidate:
        return False
    fragments = ["drink", "alc", "machin", "preg", "defect", "consum", "bever"]
    hits = sum(1 for fragment in fragments if fragment in normalized_candidate)
    return hits >= 2


def _has_warning_terminal_health_clause(normalized_candidate: str) -> bool:
    return any(
        _warning_chunk_present(normalized_candidate, phrase)
        for phrase in ("may cause health problems", "health problems")
    )


def _has_truncated_warning_anchor(normalized_candidate: str) -> bool:
    if "warning" not in normalized_candidate:
        return False
    fragments = ["surgeon", "drink", "alc", "preg", "birth", "defect", "consum", "bever", "machin"]
    hits = sum(1 for fragment in fragments if fragment in normalized_candidate)
    return hits >= 3


def _length_ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    shorter = min(len(left), len(right))
    longer = max(len(left), len(right))
    return shorter / longer


def _group_same_line_boxes(ocr_boxes: list[OCRTextBox]) -> list[list[OCRTextBox]]:
    sorted_boxes = _sort_reading_order(ocr_boxes)
    lines: list[list[OCRTextBox]] = []

    for box in sorted_boxes:
        center_y = _center_y(box.bbox)
        height = max(_max_y(box.bbox) - _min_y(box.bbox), 1.0)

        for line in lines:
            line_center = sum(_center_y(item.bbox) for item in line) / len(line)
            line_height = sum(_max_y(item.bbox) - _min_y(item.bbox) for item in line) / len(line)
            if abs(center_y - line_center) <= max(height, line_height) * 0.6:
                line.append(box)
                line.sort(key=lambda item: _min_x(item.bbox))
                break
        else:
            lines.append([box])

    return lines


def _adjacent_candidates(
    line: list[OCRTextBox],
    *,
    max_group_size: int,
) -> list[MatchCandidate]:
    candidates: list[MatchCandidate] = []
    if len(line) < 2:
        return candidates

    upper_bound = min(len(line), max_group_size)
    for size in range(2, upper_bound + 1):
        if len(line) < size:
            continue
        for start in range(0, len(line) - size + 1):
            group = line[start : start + size]
            candidates.append(_candidate_from_boxes(group, "adjacent_group"))
    return candidates


def _cross_line_candidates(
    lines: list[list[OCRTextBox]],
    *,
    max_group_size: int,
) -> list[MatchCandidate]:
    candidates: list[MatchCandidate] = []
    if len(lines) < 2:
        return candidates

    ordered_lines = sorted(lines, key=_line_sort_key)
    ordered_boxes: list[OCRTextBox] = []
    line_indexes: dict[int, int] = {}
    for line_index, line in enumerate(ordered_lines):
        for box in sorted(line, key=lambda item: _min_x(item.bbox)):
            ordered_boxes.append(box)
            line_indexes[id(box)] = line_index

    upper_bound = min(len(ordered_boxes), max_group_size)
    for size in range(2, upper_bound + 1):
        for start in range(0, len(ordered_boxes) - size + 1):
            group = ordered_boxes[start : start + size]
            group_line_count = _group_line_count(group, line_indexes)
            if group_line_count < 2:
                continue
            candidates.append(
                _candidate_from_boxes(
                    group,
                    "cross_line_group",
                    line_count=group_line_count,
                    preserve_order=True,
                )
            )
    return candidates


def _stacked_line_candidates(lines: list[list[OCRTextBox]]) -> list[MatchCandidate]:
    candidates: list[MatchCandidate] = []
    if len(lines) < 2:
        return candidates

    ordered_lines = sorted(lines, key=_line_sort_key)
    for upper_line, lower_line in zip(ordered_lines, ordered_lines[1:]):
        for upper in upper_line:
            for lower in lower_line:
                if _horizontally_aligned(upper, lower):
                    candidates.append(
                        _candidate_from_boxes(
                            [upper, lower],
                            "cross_line_group",
                            line_count=2,
                            preserve_order=True,
                        )
                    )
    return candidates


def _separator_split_candidates(candidates: list[MatchCandidate]) -> list[MatchCandidate]:
    split_candidates: list[MatchCandidate] = []
    for candidate in candidates:
        if candidate.source == "full_text":
            continue
        parts = [part.strip() for part in _TEXT_SEPARATOR_RE.split(candidate.text)]
        for part in parts:
            if not part or part == candidate.text:
                continue
            split_candidates.append(
                MatchCandidate(
                    part,
                    candidate.ocr_confidence,
                    candidate.bbox,
                    "split_text",
                    candidate.line_count,
                )
            )
    return split_candidates


def _candidate_from_boxes(
    boxes: list[OCRTextBox],
    source: str,
    *,
    line_count: int = 1,
    preserve_order: bool = False,
) -> MatchCandidate:
    ordered = boxes if preserve_order else sorted(boxes, key=lambda item: _min_x(item.bbox))
    text = _join_ordered_box_texts(ordered) if preserve_order else _join_box_texts(ordered)
    confidence = sum(box.confidence for box in ordered) / len(ordered)
    return MatchCandidate(
        text,
        confidence,
        _combined_bbox([box.bbox for box in ordered]),
        source,
        line_count,
    )


def _combined_bbox(boxes: list[BBox]) -> BBox:
    points = [point for bbox in boxes for point in bbox]
    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    return [[min_x, min_y], [max_x, min_y], [max_x, max_y], [min_x, max_y]]


def _sort_reading_order(ocr_boxes: list[OCRTextBox]) -> list[OCRTextBox]:
    return sorted(ocr_boxes, key=lambda box: (_center_y(box.bbox), _min_x(box.bbox)))


def _dedupe_candidates(candidates: list[MatchCandidate]) -> list[MatchCandidate]:
    seen: set[tuple[str, str]] = set()
    deduped: list[MatchCandidate] = []
    for candidate in candidates:
        key = (candidate.source, normalize_text(candidate.text))
        if key not in seen:
            seen.add(key)
            deduped.append(candidate)
    return deduped


def _min_x(bbox: BBox) -> float:
    return min(point[0] for point in bbox)


def _min_y(bbox: BBox) -> float:
    return min(point[1] for point in bbox)


def _max_y(bbox: BBox) -> float:
    return max(point[1] for point in bbox)


def _center_y(bbox: BBox) -> float:
    return (_min_y(bbox) + _max_y(bbox)) / 2.0


def _max_x(bbox: BBox) -> float:
    return max(point[0] for point in bbox)


def _height(bbox: BBox) -> float:
    return max(_max_y(bbox) - _min_y(bbox), 1.0)


def _line_sort_key(line: list[OCRTextBox]) -> tuple[float, float]:
    return (
        sum(_center_y(item.bbox) for item in line) / len(line),
        min(_min_x(item.bbox) for item in line),
    )


def _group_line_count(group: list[OCRTextBox], line_indexes: dict[int, int]) -> int:
    indexes = [line_indexes[id(box)] for box in group]
    return max(indexes) - min(indexes) + 1


def _horizontally_aligned(upper: OCRTextBox, lower: OCRTextBox) -> bool:
    upper_left = _min_x(upper.bbox)
    upper_right = _max_x(upper.bbox)
    lower_left = _min_x(lower.bbox)
    lower_right = _max_x(lower.bbox)
    overlap = min(upper_right, lower_right) - max(upper_left, lower_left)
    if overlap > 0:
        return True

    upper_center = (upper_left + upper_right) / 2.0
    lower_center = (lower_left + lower_right) / 2.0
    upper_width = max(upper_right - upper_left, 1.0)
    lower_width = max(lower_right - lower_left, 1.0)
    return abs(upper_center - lower_center) <= max(upper_width, lower_width) * 0.6


def _join_box_texts(boxes: list[OCRTextBox]) -> str:
    if not boxes:
        return ""

    text = boxes[0].text
    for left, right in zip(boxes, boxes[1:]):
        text += _separator_for_boxes(left, right) + right.text
    return text


def _separator_for_boxes(left: OCRTextBox, right: OCRTextBox) -> str:
    gap = _min_x(right.bbox) - _max_x(left.bbox)
    char_width_scale = min(_estimated_char_width(left), _estimated_char_width(right))
    if gap <= char_width_scale * 0.35:
        return ""

    if left.text.endswith(("-", "/", "#")):
        return ""

    return " "


def _join_ordered_box_texts(boxes: list[OCRTextBox]) -> str:
    if not boxes:
        return ""

    text = boxes[0].text
    for left, right in zip(boxes, boxes[1:]):
        if _same_line(left, right):
            text += _separator_for_boxes(left, right) + right.text
        else:
            text += " " + right.text
    return text


def _same_line(left: OCRTextBox, right: OCRTextBox) -> bool:
    left_height = _height(left.bbox)
    right_height = _height(right.bbox)
    return abs(_center_y(left.bbox) - _center_y(right.bbox)) <= max(left_height, right_height) * 0.6


def _target_group_limit(targets: list[str]) -> int:
    if not targets:
        return 4

    token_counts = [len(target.split()) for target in targets if target.strip()]
    if not token_counts:
        return 4

    return min(max(max(token_counts) * 2, 4), 8)


def _estimated_char_width(box: OCRTextBox) -> float:
    text_length = max(len(box.text.strip()), 1)
    return max((_max_x(box.bbox) - _min_x(box.bbox)) / text_length, 1.0)
