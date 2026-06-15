from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import APIModel


class ImageFileRead(APIModel):
    path: str
    name: str
    size_bytes: int = Field(alias="sizeBytes")
    modified: datetime
    preview_url: str = Field(alias="previewUrl")
