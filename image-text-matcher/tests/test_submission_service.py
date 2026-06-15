from __future__ import annotations

from datetime import UTC, datetime

from app.db.models import ProcessResult, QueueItem


def submission_payload(**overrides):
    payload = {
        "brand": "Brand",
        "classType": "Wine",
        "address": "123 Main",
        "netContents": "750ml",
        "alcohol": "12%",
        "origin": "France",
        "appellation": "Bordeaux",
        "warning": "Government warning",
        "category": "Red Wine",
        "images": "label-front.png",
    }
    payload.update(overrides)
    return payload


def test_post_submissions_accepts_single_object(client) -> None:
    response = client.post("/submissions", json=submission_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["classType"] == "Wine"
    assert body["netContents"] == "750ml"
    assert body["images"] == "label-front.png"


def test_post_submissions_accepts_array(client) -> None:
    response = client.post(
        "/submissions",
        json=[
            submission_payload(brand="First"),
            submission_payload(brand="Second", images="label-back.png"),
        ],
    )

    assert response.status_code == 201
    body = response.json()
    assert len(body) == 2
    assert [item["brand"] for item in body] == ["First", "Second"]


def test_queue_item_created_when_submission_is_created(client) -> None:
    create_response = client.post("/submissions", json=submission_payload())
    submission_id = create_response.json()["id"]

    queue_response = client.get("/queue")

    assert queue_response.status_code == 200
    items = queue_response.json()
    assert len(items) == 1
    assert items[0]["submissionId"] == submission_id
    assert items[0]["status"] == "queued"


def test_delete_submission_cascades_process_results_and_queue_items(client, db_session) -> None:
    create_response = client.post("/submissions", json=submission_payload())
    submission_id = create_response.json()["id"]
    queue_item_id = client.get("/queue").json()[0]["id"]

    db_session.add(
        ProcessResult(
            submission_id=submission_id,
            combined_image="/data/processed/test.png",
            match_results=[],
            approved=False,
            process_started=datetime.now(UTC),
            status="failed",
        )
    )
    db_session.commit()

    delete_response = client.delete(f"/submissions/{submission_id}")

    assert delete_response.status_code == 204
    assert db_session.get(QueueItem, queue_item_id) is None
    assert db_session.query(ProcessResult).count() == 0


def test_patch_submission_allows_wine_without_appellation(client) -> None:
    create_response = client.post(
        "/submissions",
        json=submission_payload(category="Malt Beverage", appellation=None),
    )
    submission_id = create_response.json()["id"]

    update_response = client.patch(
        f"/submissions/{submission_id}",
        json={"category": "Wine"},
    )

    assert update_response.status_code == 200
    assert update_response.json()["category"] == "Wine"
    assert update_response.json()["appellation"] is None


def test_post_submission_allows_missing_alcohol(client) -> None:
    payload = submission_payload()
    payload.pop("alcohol")

    response = client.post("/submissions", json=payload)

    assert response.status_code == 201
    assert response.json()["alcohol"] is None
