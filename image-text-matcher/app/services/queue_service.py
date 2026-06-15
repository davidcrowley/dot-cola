from __future__ import annotations

from datetime import datetime, timezone
from collections.abc import Callable

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import QueueItem, Submission


QueueNotifier = Callable[[], None]
_queue_notifier: QueueNotifier | None = None


def set_queue_notifier(notifier: QueueNotifier | None) -> None:
    global _queue_notifier
    _queue_notifier = notifier


def notify_queue_item_available() -> None:
    if _queue_notifier is not None:
        _queue_notifier()


def create_queue_item(db: Session, submission_id: int) -> QueueItem:
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    active_item = db.scalars(
        select(QueueItem)
        .where(
            QueueItem.submission_id == submission_id,
            QueueItem.status.in_(["queued", "processing"]),
        )
        .order_by(QueueItem.created.asc(), QueueItem.id.asc())
    ).first()
    if active_item is not None:
        raise HTTPException(status_code=409, detail="Submission is already in the queue")

    queue_item = QueueItem(submission_id=submission_id, status="queued")
    db.add(queue_item)
    db.commit()
    db.refresh(queue_item)
    notify_queue_item_available()
    return queue_item


def list_queue_items(db: Session) -> list[QueueItem]:
    stmt = (
        select(QueueItem)
        .where(QueueItem.status.in_(["queued", "processing"]))
        .order_by(QueueItem.created.asc(), QueueItem.id.asc())
    )
    return list(db.scalars(stmt))


def cancel_queue_item_for_submission(db: Session, submission_id: int) -> QueueItem:
    stmt = (
        select(QueueItem)
        .where(
            QueueItem.submission_id == submission_id,
            QueueItem.status == "queued",
        )
        .order_by(QueueItem.created.asc(), QueueItem.id.asc())
    )
    queue_item = db.scalars(stmt).first()
    if queue_item is None:
        raise HTTPException(status_code=404, detail="No queued item found for submission")

    queue_item.status = "cancelled"
    queue_item.completed = datetime.now(timezone.utc)
    db.commit()
    db.refresh(queue_item)
    return queue_item


def clear_pending_queue(db: Session) -> int:
    queued_items = list(
        db.scalars(select(QueueItem).where(QueueItem.status == "queued").order_by(QueueItem.id.asc()))
    )
    completed = datetime.now(timezone.utc)
    for item in queued_items:
        item.status = "cancelled"
        item.completed = completed
    db.commit()
    return len(queued_items)
