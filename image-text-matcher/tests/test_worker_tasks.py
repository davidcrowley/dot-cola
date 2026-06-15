from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy.orm import sessionmaker

from app.db.models import QueueItem, Submission
from app.worker import background


def _submission() -> Submission:
    return Submission(
        brand="Brand",
        class_type="Wine",
        address="123 Main",
        net_contents="750ml",
        alcohol="12%",
        warning="Government warning",
        category="Red Wine",
        images="label-front.png",
    )


def test_background_worker_processes_next_queued_item(db_session, monkeypatch) -> None:
    submission = _submission()
    db_session.add(submission)
    db_session.commit()
    db_session.refresh(submission)

    queue_item = QueueItem(submission_id=submission.id, status="queued")
    db_session.add(queue_item)
    db_session.commit()
    db_session.refresh(queue_item)

    testing_session_local = sessionmaker(
        bind=db_session.get_bind(),
        autoflush=False,
        autocommit=False,
        future=True,
    )

    def fake_process_queue_item(db, item):
        item.status = "complete"
        item.started = datetime.now(UTC)
        item.completed = datetime.now(UTC)
        db.commit()
        return SimpleNamespace(status="complete")

    monkeypatch.setattr(background, "SessionLocal", testing_session_local)
    monkeypatch.setattr(background, "process_queue_item", fake_process_queue_item)

    worker = background.BackgroundQueueWorker(poll_interval_seconds=0.01)

    assert worker.run_once() is True

    db_session.expire_all()
    assert db_session.get(QueueItem, queue_item.id).status == "complete"


def test_background_worker_health_reports_online_after_start(monkeypatch) -> None:
    worker = background.BackgroundQueueWorker(poll_interval_seconds=10)
    monkeypatch.setattr(worker, "recover_interrupted_work", lambda: None)
    monkeypatch.setattr(worker, "run_once", lambda: False)

    worker.start()
    try:
        health = worker.health()
        assert health["worker_available"] is True
        assert health["worker_status"] == "online"
        assert health["worker_count"] == 1
    finally:
        worker.stop()
