from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import require_authenticated
from app.db.models import QueueItem, Submission
from app.db.session import get_db
from app.schemas.admin import DashboardStatsRead, ProcessingStatusRead
from app.services.admin_service import get_processing_status, get_worker_health, set_processing_enabled


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/processing-status", response_model=ProcessingStatusRead)
def processing_status(
    _: None = Depends(require_authenticated),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return get_processing_status(db)


@router.post("/processing/pause", response_model=ProcessingStatusRead)
def pause_processing(
    _: None = Depends(require_authenticated),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    set_processing_enabled(db, False)
    return get_processing_status(db)


@router.post("/processing/resume", response_model=ProcessingStatusRead)
def resume_processing(
    _: None = Depends(require_authenticated),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    set_processing_enabled(db, True)
    return get_processing_status(db)


@router.get("/dashboard/stats", response_model=DashboardStatsRead)
def dashboard_stats(
    _: None = Depends(require_authenticated),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    submission_count = db.scalar(select(func.count()).select_from(Submission)) or 0
    queue_count = (
        db.scalar(
            select(func.count()).select_from(QueueItem).where(QueueItem.status.in_(["queued", "processing"]))
        )
        or 0
    )
    status = get_processing_status(db)
    worker = get_worker_health()
    return {
        "submission_count": submission_count,
        "queue_count": queue_count,
        "processing_enabled": status["processing_enabled"],
        "worker_available": worker["worker_available"],
        "worker_status": worker["worker_status"],
        "worker_count": worker["worker_count"],
    }
