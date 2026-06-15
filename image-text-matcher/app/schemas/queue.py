from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import APIModel


class QueueItemRead(APIModel):
    id: int
    submission_id: int = Field(alias="submissionId")
    status: str
    created: datetime
    updated: datetime
    started: datetime | None = None
    completed: datetime | None = None
    error_message: str | None = Field(alias="errorMessage", default=None)
