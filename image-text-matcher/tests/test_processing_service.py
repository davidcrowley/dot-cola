from __future__ import annotations

import subprocess
from datetime import UTC, datetime

import numpy as np
import pytest

from app.db.models import QueueItem, Submission
from app.models import OCRTextBox
from app.config import get_settings
from app.services.admin_service import get_processing_status, set_processing_enabled
from app.services.processing_service import (
    _extract_front_label_crop_text,
    _extract_warning_crop_text,
    _map_clockwise_scaled_crop_boxes,
    _map_scaled_crop_boxes,
    _map_rotated_bbox,
    _targets_for_submission,
    process_queue_item,
    run_processing_job,
)


def test_processing_status_defaults_and_can_pause(db_session) -> None:
    status = get_processing_status(db_session)
    assert status["processing_enabled"] is True

    set_processing_enabled(db_session, False)
    paused = get_processing_status(db_session)
    assert paused["processing_enabled"] is False
    assert paused["status"] == "paused"


def test_process_queue_item_marks_result_failed_when_job_raises(db_session, monkeypatch) -> None:
    submission = Submission(
        brand="Brand",
        class_type="Wine",
        address="123 Main",
        net_contents="750ml",
        alcohol="12%",
        origin="France",
        appellation="Bordeaux",
        warning="Government warning",
        category="Wine",
        images="label-front.png",
        created=datetime.now(UTC),
    )
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
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("PaddleOCR model files are missing")),
    )

    with pytest.raises(RuntimeError, match="PaddleOCR model files are missing"):
        process_queue_item(db_session, queue_item)

    db_session.refresh(queue_item)
    result = submission.process_results[0]
    assert queue_item.status == "failed"
    assert queue_item.error_message == "PaddleOCR model files are missing"
    assert result.status == "failed"
    assert result.error_message == "PaddleOCR model files are missing"


def test_run_processing_job_raises_timeout_error(monkeypatch) -> None:
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=90)

    monkeypatch.setattr(get_settings(), "processing_job_subprocess", True)
    monkeypatch.setattr("app.services.processing_service.subprocess.run", fake_run)

    with pytest.raises(RuntimeError, match="timed out after"):
        run_processing_job(
            combined_image_path="/tmp/result.png",
            targets=[],
            match_threshold=85,
        )


def test_targets_for_submission_excludes_category() -> None:
    submission = Submission(
        brand="Meyer Brewing",
        class_type="Lager",
        address="Bloomington, ILL",
        net_contents="1 Pint",
        alcohol="5.0% Alc. by Vol.",
        origin=None,
        appellation=None,
        warning="Government warning",
        category="Malt Beverage",
        images="label.png",
        created=datetime.now(UTC),
    )

    fields = [target["field"] for target in _targets_for_submission(submission)]

    assert "category" not in fields
    assert "classType" in fields


def test_rotated_clockwise_bbox_maps_back_to_original_coordinates() -> None:
    bbox = [[90.0, 10.0], [90.0, 20.0], [60.0, 20.0], [60.0, 10.0]]

    mapped = _map_rotated_bbox(
        bbox,
        width=200,
        height=100,
        rotation="clockwise",
    )

    assert mapped == [[10.0, 10.0], [20.0, 10.0], [20.0, 40.0], [10.0, 40.0]]


def test_rotated_counterclockwise_bbox_maps_back_to_original_coordinates() -> None:
    bbox = [[10.0, 190.0], [10.0, 180.0], [40.0, 180.0], [40.0, 190.0]]

    mapped = _map_rotated_bbox(
        bbox,
        width=200,
        height=100,
        rotation="counterclockwise",
    )

    assert mapped == [[10.0, 10.0], [20.0, 10.0], [20.0, 40.0], [10.0, 40.0]]


def test_scaled_crop_boxes_map_back_to_original_coordinates() -> None:
    boxes = [
        OCRTextBox(
            text="GOVERNM",
            confidence=0.9,
            bbox=[[30.0, 60.0], [90.0, 60.0], [90.0, 90.0], [30.0, 90.0]],
        )
    ]

    mapped = _map_scaled_crop_boxes(boxes, left=100, top=200, scale=3.0)

    assert mapped[0].bbox == [
        [110.0, 220.0],
        [130.0, 220.0],
        [130.0, 230.0],
        [110.0, 230.0],
    ]


def test_front_label_crop_text_maps_back_to_original_coordinates() -> None:
    class FakeEngine:
        def extract_text(self, image):
            return [
                OCRTextBox(
                    text="NOMA.COUNTY",
                    confidence=0.95,
                    bbox=[[80.0, 40.0], [240.0, 40.0], [240.0, 80.0], [80.0, 80.0]],
                )
            ]

    image = np.zeros((500, 1000, 3), dtype=np.uint8)

    boxes = _extract_front_label_crop_text(FakeEngine(), image)

    assert boxes
    assert boxes[0].text == "NOMA.COUNTY"
    assert boxes[0].bbox == [
        [100.0, 457.0],
        [120.0, 457.0],
        [120.0, 462.0],
        [100.0, 462.0],
    ]


def test_warning_crop_text_includes_lower_right_warning_area() -> None:
    class FakeEngine:
        def extract_text(self, image):
            return [
                OCRTextBox(
                    text="GOVERNMENT WARNING",
                    confidence=0.95,
                    bbox=[[40.0, 40.0], [240.0, 40.0], [240.0, 80.0], [40.0, 80.0]],
                ),
                OCRTextBox(
                    text="HEALTH PROBLEMS",
                    confidence=0.93,
                    bbox=[[40.0, 100.0], [220.0, 100.0], [220.0, 140.0], [40.0, 140.0]],
                )
            ]

    image = np.zeros((500, 1000, 3), dtype=np.uint8)

    boxes = _extract_warning_crop_text(FakeEngine(), image)

    assert any(
        box.text == "GOVERNMENT WARNING"
        and min(point[1] for point in box.bbox) >= 390
        for box in boxes
    )
    assert any(
        box.text == "GOVERNMENT WARNING HEALTH PROBLEMS"
        and min(point[1] for point in box.bbox) >= 390
        for box in boxes
    )


def test_clockwise_scaled_crop_boxes_map_back_to_original_coordinates() -> None:
    boxes = [
        OCRTextBox(
            text="WARNING",
            confidence=0.9,
            bbox=[[40.0, 80.0], [120.0, 80.0], [120.0, 160.0], [40.0, 160.0]],
        )
    ]

    mapped = _map_clockwise_scaled_crop_boxes(
        boxes,
        left=800,
        top=100,
        crop_height=300,
        scale=4.0,
    )

    assert mapped[0].bbox == [
        [820.0, 390.0],
        [820.0, 370.0],
        [840.0, 370.0],
        [840.0, 390.0],
    ]
