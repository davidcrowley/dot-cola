from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_authenticated
from app.db.session import get_db
from app.schemas.queue import QueueItemRead
from app.services.queue_service import cancel_queue_item_for_submission, clear_pending_queue, create_queue_item, list_queue_items


router = APIRouter(tags=["queue"])


@router.get("/queue", response_model=list[QueueItemRead])
def get_queue(
    _: None = Depends(require_authenticated),
    db: Session = Depends(get_db),
) -> list:
    return list_queue_items(db)


@router.post("/queue/{submission_id}", response_model=QueueItemRead, status_code=201)
def enqueue_submission(
    submission_id: int,
    _: None = Depends(require_authenticated),
    db: Session = Depends(get_db),
):
    return create_queue_item(db, submission_id)


@router.delete("/queue/{submission_id}", response_model=QueueItemRead)
def remove_queued_submission(
    submission_id: int,
    _: None = Depends(require_authenticated),
    db: Session = Depends(get_db),
):
    return cancel_queue_item_for_submission(db, submission_id)


@router.delete("/queue")
def clear_queue(
    _: None = Depends(require_authenticated),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    return {"cancelled": clear_pending_queue(db)}
