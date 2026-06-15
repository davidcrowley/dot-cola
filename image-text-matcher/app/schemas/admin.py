from __future__ import annotations

from app.schemas.common import APIModel


class ProcessingStatusRead(APIModel):
    processing_enabled: bool
    status: str


class DashboardStatsRead(APIModel):
    submission_count: int
    queue_count: int
    processing_enabled: bool
    worker_available: bool
    worker_status: str
    worker_count: int
