from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event, Lock, Thread

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import ProcessResult, QueueItem
from app.db.session import SessionLocal
from app.services.admin_service import is_processing_enabled
from app.services.processing_service import process_queue_item


logger = logging.getLogger(__name__)


@dataclass
class WorkerSnapshot:
    running: bool = False
    current_queue_item_id: int | None = None
    last_started_at: datetime | None = None
    last_completed_at: datetime | None = None
    last_error: str | None = None


class BackgroundQueueWorker:
    def __init__(self, poll_interval_seconds: float | None = None) -> None:
        self.poll_interval_seconds = poll_interval_seconds or get_settings().queue_poll_interval_seconds
        self._stop_event = Event()
        self._wake_event = Event()
        self._thread: Thread | None = None
        self._lock = Lock()
        self._snapshot = WorkerSnapshot()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._wake_event.clear()
        self._thread = Thread(target=self._run_forever, name="queue-worker", daemon=True)
        with self._lock:
            self._snapshot.running = True
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        with self._lock:
            self._snapshot.running = False
            self._snapshot.current_queue_item_id = None

    def wake(self) -> None:
        self._wake_event.set()

    def health(self) -> dict[str, object]:
        with self._lock:
            running = self._snapshot.running
            return {
                "worker_available": running,
                "worker_status": "online" if running else "offline",
                "worker_count": 1 if running else 0,
                "current_queue_item_id": self._snapshot.current_queue_item_id,
                "last_started_at": self._snapshot.last_started_at,
                "last_completed_at": self._snapshot.last_completed_at,
                "last_error": self._snapshot.last_error,
            }

    def recover_interrupted_work(self) -> None:
        db = SessionLocal()
        try:
            recover_interrupted_work(db)
        finally:
            db.close()

    def run_once(self) -> bool:
        db = SessionLocal()
        try:
            if not is_processing_enabled(db):
                return False

            queue_item = _next_queued_item(db)
            if queue_item is None:
                return False

            self._mark_started(queue_item.id)
            try:
                process_queue_item(db, queue_item)
            except Exception as exc:
                self._mark_error(exc)
                logger.exception("Queue item %s failed", queue_item.id)
            else:
                self._mark_completed()
            return True
        finally:
            db.close()

    def _run_forever(self) -> None:
        with self._lock:
            self._snapshot.running = True

        try:
            self.recover_interrupted_work()
            while not self._stop_event.is_set():
                worked = self.run_once()
                if not worked:
                    self._wake_event.wait(self.poll_interval_seconds)
                    self._wake_event.clear()
        finally:
            with self._lock:
                self._snapshot.running = False
                self._snapshot.current_queue_item_id = None

    def _mark_started(self, queue_item_id: int) -> None:
        with self._lock:
            self._snapshot.current_queue_item_id = queue_item_id
            self._snapshot.last_started_at = datetime.now(timezone.utc)
            self._snapshot.last_error = None

    def _mark_completed(self) -> None:
        with self._lock:
            self._snapshot.current_queue_item_id = None
            self._snapshot.last_completed_at = datetime.now(timezone.utc)

    def _mark_error(self, exc: Exception) -> None:
        with self._lock:
            self._snapshot.current_queue_item_id = None
            self._snapshot.last_completed_at = datetime.now(timezone.utc)
            self._snapshot.last_error = str(exc)


def _next_queued_item(db: Session) -> QueueItem | None:
    stmt = (
        select(QueueItem)
        .where(QueueItem.status == "queued")
        .order_by(QueueItem.created.asc(), QueueItem.id.asc())
        .with_for_update(skip_locked=True)
    )
    return db.scalars(stmt).first()


def recover_interrupted_work(db: Session) -> int:
    now = datetime.now(timezone.utc)
    processing_items = list(db.scalars(select(QueueItem).where(QueueItem.status == "processing")))
    processing_results = list(db.scalars(select(ProcessResult).where(ProcessResult.status == "processing")))

    for item in processing_items:
        item.status = "queued"
        item.started = None
        item.error_message = "Recovered from interrupted processing run"

    for result in processing_results:
        result.status = "failed"
        result.process_completed = now
        result.error_message = "Processing was interrupted before completion"

    db.commit()
    return len(processing_items)
