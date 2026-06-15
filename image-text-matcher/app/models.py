from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Point = list[float]
BBox = list[Point]


class OCRTextBox(BaseModel):
    text: str
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: BBox


class MatchResult(BaseModel):
    target: str
    found: bool
    matched_text: str | None
    closest_text: str | None = None
    score: float
    ocr_confidence: float | None
    combined_confidence: float | None
    bbox: BBox | None
    candidate_source: Literal[
        "single_box",
        "line_group",
        "adjacent_group",
        "cross_line_group",
        "split_text",
        "full_text",
    ]


class AnalyzeImageResponse(BaseModel):
    filename: str
    ocr_engine: str
    match_threshold: int
    matches: list[MatchResult]
    raw_ocr_count: int
