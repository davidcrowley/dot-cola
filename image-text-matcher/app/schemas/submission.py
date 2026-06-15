from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from app.config import DEFAULT_GOVERNMENT_WARNING
from app.schemas.common import APIModel
from app.schemas.process_result import ProcessResultRead


class SubmissionBase(APIModel):
    brand: str
    class_type: str = Field(alias="classType")
    address: str
    net_contents: str = Field(alias="netContents")
    alcohol: str | None = None
    origin: str | None = None
    appellation: str | None = None
    warning: str = DEFAULT_GOVERNMENT_WARNING
    category: str
    images: str

    @field_validator("images")
    @classmethod
    def validate_images(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("images must include a path")
        return cleaned

    @field_validator("alcohol", "origin", "appellation", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("warning", mode="before")
    @classmethod
    def normalize_warning(cls, value: str | None) -> str:
        return DEFAULT_GOVERNMENT_WARNING

class SubmissionCreate(SubmissionBase):
    pass


class SubmissionUpdate(APIModel):
    brand: str | None = None
    class_type: str | None = Field(alias="classType", default=None)
    address: str | None = None
    net_contents: str | None = Field(alias="netContents", default=None)
    alcohol: str | None = None
    origin: str | None = None
    appellation: str | None = None
    warning: str | None = None
    category: str | None = None
    images: str | None = None
    approved: bool | None = None
    processed: datetime | None = None

    @field_validator("images")
    @classmethod
    def validate_images(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("images must include a path")
        return cleaned

    @field_validator("alcohol", "origin", "appellation", mode="before")
    @classmethod
    def normalize_optional_update_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("warning", mode="before")
    @classmethod
    def normalize_update_warning(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return DEFAULT_GOVERNMENT_WARNING


class SubmissionRead(SubmissionBase):
    id: int
    created: datetime
    processed: datetime | None = None
    approved: bool | None = None
    process_results: list[ProcessResultRead] | None = Field(alias="processResults", default=None)
