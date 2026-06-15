from __future__ import annotations

from datetime import UTC, datetime

from app.db.models import QueueItem, Submission
from app.services.processing_service import _targets_for_submission, process_queue_item


def _submission(**overrides) -> Submission:
    values = {
        "brand": "Brand",
        "class_type": "Wine",
        "address": "123 Main",
        "net_contents": "750ml",
        "alcohol": "12%",
        "origin": "France",
        "appellation": "Bordeaux",
        "warning": "Government warning",
        "category": "Wine",
        "images": "label-front.png",
        "created": datetime.now(UTC),
    }
    values.update(overrides)
    return Submission(**values)


def _match(found: bool, matched_text: str | None, bbox: list[list[float]] | None = None) -> dict[str, object]:
    return {
        "matched": found,
        "found": found,
        "matched_text": matched_text,
        "fuzzy_score": 0.97 if found else 0.4,
        "ocr_confidence": 0.95 if found else 0.4,
        "combined_confidence": 0.96 if found else 0.4,
        "bbox": bbox,
        "candidate_source": "ocr",
    }


def test_process_queue_item_requires_origin_when_present(db_session, monkeypatch) -> None:
    submission = _submission(origin="France", category="Malt Beverage", appellation=None)
    db_session.add(submission)
    db_session.commit()
    db_session.refresh(submission)

    queue_item = QueueItem(submission_id=submission.id, status="queued")
    db_session.add(queue_item)
    db_session.commit()
    db_session.refresh(queue_item)

    monkeypatch.setattr("app.services.processing_service.build_submission_image", lambda *args: "/tmp/result.png")
    monkeypatch.setattr(
        "app.services.processing_service.run_processing_job",
        lambda **kwargs: {
            "approved": False,
            "match_results": [
                {"field": "brand", "label": "Brand", "required": True, "expected_text": "Brand", "feedback_message": "ok", **_match(True, "Brand")},
                {"field": "classType", "label": "Class Type", "required": True, "expected_text": "Wine", "feedback_message": "ok", **_match(True, "Wine")},
                {"field": "address", "label": "Address", "required": True, "expected_text": "123 Main", "feedback_message": "ok", **_match(True, "123 Main")},
                {"field": "netContents", "label": "Net Contents", "required": True, "expected_text": "750ml", "feedback_message": "ok", **_match(True, "750ml")},
                {"field": "alcohol", "label": "Alcohol", "required": True, "expected_text": "12%", "feedback_message": "ok", **_match(True, "12%")},
                {"field": "warning", "label": "Government Warning", "required": True, "expected_text": "Government warning", "feedback_message": "ok", **_match(True, "Government warning")},
                {"field": "category", "label": "Category", "required": True, "expected_text": "Malt Beverage", "feedback_message": "ok", **_match(True, "Malt Beverage")},
                {"field": "origin", "label": "Origin", "required": True, "expected_text": "France", "feedback_message": "missing", **_match(False, None)},
            ],
        },
    )

    result = process_queue_item(db_session, queue_item)

    assert result.approved is False
    assert result.match_results[-1]["field"] == "origin"
    assert result.match_results[-1]["required"] is True
    assert result.match_results[-1]["matched"] is False


def test_process_queue_item_requires_appellation_for_wine_and_exposes_ui_metadata(db_session, monkeypatch) -> None:
    submission = _submission()
    db_session.add(submission)
    db_session.commit()
    db_session.refresh(submission)

    queue_item = QueueItem(submission_id=submission.id, status="queued")
    db_session.add(queue_item)
    db_session.commit()
    db_session.refresh(queue_item)

    monkeypatch.setattr("app.services.processing_service.build_submission_image", lambda *args: "/tmp/result.png")
    monkeypatch.setattr(
        "app.services.processing_service.run_processing_job",
        lambda **kwargs: {
            "approved": True,
            "match_results": [
                {"field": "brand", "label": "Brand", "required": True, "expected_text": "Brand", "feedback_message": "ok", **_match(True, "Brand", [[1.0, 2.0], [3.0, 4.0]])},
                {"field": "classType", "label": "Class Type", "required": True, "expected_text": "Wine", "feedback_message": "ok", **_match(True, "Wine")},
                {"field": "address", "label": "Address", "required": True, "expected_text": "123 Main", "feedback_message": "ok", **_match(True, "123 Main")},
                {"field": "netContents", "label": "Net Contents", "required": True, "expected_text": "750ml", "feedback_message": "ok", **_match(True, "750ml")},
                {"field": "alcohol", "label": "Alcohol", "required": True, "expected_text": "12%", "feedback_message": "ok", **_match(True, "12%")},
                {"field": "warning", "label": "Government Warning", "required": True, "expected_text": "Government warning", "feedback_message": "ok", **_match(True, "Government warning")},
                {"field": "category", "label": "Category", "required": True, "expected_text": "Wine", "feedback_message": "ok", **_match(True, "Wine")},
                {"field": "origin", "label": "Origin", "required": True, "expected_text": "France", "feedback_message": "ok", **_match(True, "France")},
                {"field": "appellation", "label": "Appellation", "required": True, "expected_text": "Bordeaux", "feedback_message": "ok", **_match(True, "Bordeaux", [[10.0, 20.0], [30.0, 40.0]])},
            ],
        },
    )

    result = process_queue_item(db_session, queue_item)

    assert result.approved is True
    appellation_result = next(item for item in result.match_results if item["field"] == "appellation")
    assert appellation_result["label"] == "Appellation"
    assert appellation_result["required"] is True
    assert appellation_result["matched"] is True
    assert appellation_result["bbox"] == [[10.0, 20.0], [30.0, 40.0]]


def test_optional_alcohol_and_appellation_are_only_targeted_when_provided() -> None:
    submission = _submission(alcohol=None, appellation=None, category="Wine")

    targets = _targets_for_submission(submission)

    assert "alcohol" not in {target["field"] for target in targets}
    assert "appellation" not in {target["field"] for target in targets}


def test_provided_optional_alcohol_and_appellation_are_required_targets() -> None:
    submission = _submission(alcohol="12%", appellation="Bordeaux", category="Wine")

    targets = _targets_for_submission(submission)
    required_by_field = {target["field"]: target["required"] for target in targets}

    assert required_by_field["alcohol"] is True
    assert required_by_field["appellation"] is True
