from __future__ import annotations

from app.db.models import Submission
from app.services import queue_service


def submission_payload():
    return {
        "brand": "Brand",
        "classType": "Wine",
        "address": "123 Main",
        "netContents": "750ml",
        "alcohol": "12%",
        "warning": "Government warning",
        "category": "Red Wine",
        "images": "label-front.png",
    }


def test_manual_queue_push_after_cancelling_existing_queue_item(client) -> None:
    create_response = client.post("/submissions", json=submission_payload())
    submission_id = create_response.json()["id"]
    cancel_response = client.delete(f"/queue/{submission_id}")
    assert cancel_response.status_code == 200

    response = client.post(f"/queue/{submission_id}")

    assert response.status_code == 201
    body = response.json()
    assert body["submissionId"] == submission_id
    assert body["status"] == "queued"


def test_manual_queue_push_rejects_duplicate_active_queue_item(client) -> None:
    create_response = client.post("/submissions", json=submission_payload())
    submission_id = create_response.json()["id"]

    response = client.post(f"/queue/{submission_id}")

    assert response.status_code == 409
    assert response.json()["detail"] == "Submission is already in the queue"


def test_cancelling_pending_queue_item_marks_it_cancelled(client) -> None:
    create_response = client.post("/submissions", json=submission_payload())
    submission_id = create_response.json()["id"]

    response = client.delete(f"/queue/{submission_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["submissionId"] == submission_id
    assert body["status"] == "cancelled"


def test_clearing_queue_marks_all_queued_items_cancelled(client) -> None:
    client.post("/submissions", json=submission_payload())
    client.post("/submissions", json=submission_payload())

    response = client.delete("/queue")

    assert response.status_code == 200
    assert response.json() == {"cancelled": 2}
    queue_response = client.get("/queue")
    assert queue_response.json() == []


def test_create_queue_item_notifies_live_worker(db_session, monkeypatch) -> None:
    submission = Submission(
        brand="Brand",
        class_type="Wine",
        address="123 Main",
        net_contents="750ml",
        alcohol="12%",
        origin="France",
        appellation="Bordeaux",
        warning="Government warning",
        category="Red Wine",
        images="label-front.png",
    )
    db_session.add(submission)
    db_session.commit()
    db_session.refresh(submission)

    calls: list[str] = []
    monkeypatch.setattr(queue_service, "_queue_notifier", lambda: calls.append("wake"))

    item = queue_service.create_queue_item(db_session, submission.id)

    assert item.status == "queued"
    assert calls == ["wake"]
