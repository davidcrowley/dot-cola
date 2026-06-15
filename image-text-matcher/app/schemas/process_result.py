from __future__ import annotations

from datetime import datetime

from pydantic import AliasChoices, Field

from app.schemas.common import APIModel


class MatchResultRead(APIModel):
    field: str
    label: str
    required: bool
    expected_text: str = Field(alias="expectedText")
    matched: bool = Field(validation_alias=AliasChoices("matched", "found"))
    matched_text: str | None = Field(alias="matchedText", default=None)
    closest_text: str | None = Field(alias="closestText", default=None)
    fuzzy_score: float = Field(alias="fuzzyScore")
    ocr_confidence: float | None = Field(alias="ocrConfidence", default=None)
    combined_confidence: float | None = Field(alias="combinedConfidence", default=None)
    bbox: list[list[float]] | None = None
    candidate_source: str = Field(alias="candidateSource")
    feedback_message: str = Field(alias="feedbackMessage")


class ProcessResultRead(APIModel):
    id: int
    submission_id: int = Field(alias="submissionId")
    combined_image: str = Field(alias="combinedImage")
    combined_image_url: str = Field(alias="combinedImageUrl")
    match_results: list[MatchResultRead] = Field(alias="matchResults")
    approved: bool
    process_started: datetime = Field(alias="processStarted")
    process_completed: datetime | None = Field(alias="processCompleted", default=None)
    created: datetime
    status: str
    error_message: str | None = Field(alias="errorMessage", default=None)
