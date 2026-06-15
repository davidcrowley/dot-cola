from __future__ import annotations

from datetime import datetime, timezone
import json
import subprocess
import sys
from threading import Lock

import cv2
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import ProcessResult, QueueItem, Submission
from app.models import BBox, OCRTextBox
from app.matching.matcher import MatchPolicy, match_targets
from app.ocr.engine import PaddleOCREngine
from app.ocr.preprocess import preprocess_image
from app.services.image_service import build_submission_image, load_processed_image


_engine_lock = Lock()
_engine: PaddleOCREngine | None = None
FIELD_SPECS = [
    {"attribute": "brand", "field": "brand", "label": "Brand", "required": True},
    {"attribute": "class_type", "field": "classType", "label": "Class Type", "required": True},
    {"attribute": "address", "field": "address", "label": "Address", "required": True},
    {"attribute": "net_contents", "field": "netContents", "label": "Net Contents", "required": True},
    {"attribute": "alcohol", "field": "alcohol", "label": "Alcohol", "required": True},
    {"attribute": "warning", "field": "warning", "label": "Government Warning", "required": True},
    {"attribute": "origin", "field": "origin", "label": "Origin", "required": False},
    {"attribute": "appellation", "field": "appellation", "label": "Appellation", "required": False},
]
FIELD_MATCH_POLICIES = {
    "brand": MatchPolicy(field="brand", mode="loose", max_lines=None),
    "classType": MatchPolicy(field="classType", mode="contains", max_lines=1),
    "address": MatchPolicy(field="address", mode="exactish", max_lines=2),
    "netContents": MatchPolicy(field="netContents", mode="exactish", max_lines=2),
    "alcohol": MatchPolicy(field="alcohol", mode="exactish", max_lines=2),
    "warning": MatchPolicy(field="warning", mode="warning", max_lines=None),
    "origin": MatchPolicy(field="origin", mode="exactish", max_lines=2),
    "appellation": MatchPolicy(field="appellation", mode="exactish", max_lines=2),
}


def process_queue_item(db: Session, queue_item: QueueItem) -> ProcessResult:
    submission = db.get(Submission, queue_item.submission_id)
    if submission is None:
        raise ValueError(f"Submission {queue_item.submission_id} not found")

    now = datetime.now(timezone.utc)
    queue_item.status = "processing"
    queue_item.started = now
    queue_item.error_message = None

    process_result = ProcessResult(
        submission_id=submission.id,
        combined_image="",
        match_results=[],
        approved=False,
        process_started=now,
        status="processing",
    )
    db.add(process_result)
    db.commit()
    db.refresh(queue_item)
    db.refresh(process_result)

    try:
        combined_image_path = build_submission_image(submission.images, submission.id, queue_item.id)
        process_result.combined_image = combined_image_path

        targets = _targets_for_submission(submission)
        job_result = run_processing_job(
            combined_image_path=combined_image_path,
            targets=targets,
            match_threshold=get_settings().match_threshold,
        )
        match_results = job_result["match_results"]
        approved = bool(job_result["approved"])
        completed = datetime.now(timezone.utc)
        process_result.match_results = match_results
        process_result.approved = approved
        process_result.process_completed = completed
        process_result.status = "complete"
        submission.processed = completed
        submission.approved = approved
        queue_item.status = "complete"
        queue_item.completed = completed
        db.commit()
        db.refresh(process_result)
        return process_result
    except Exception as exc:
        completed = datetime.now(timezone.utc)
        process_result.status = "failed"
        process_result.error_message = str(exc)
        process_result.process_completed = completed
        queue_item.status = "failed"
        queue_item.error_message = str(exc)
        queue_item.completed = completed
        db.commit()
        db.refresh(process_result)
        raise


def run_processing_job(
    *,
    combined_image_path: str,
    targets: list[dict[str, object]],
    match_threshold: int,
) -> dict[str, object]:
    settings = get_settings()
    if not settings.processing_job_subprocess:
        return run_ocr_pipeline(
            combined_image_path=combined_image_path,
            targets=targets,
            match_threshold=match_threshold,
        )

    payload = {
        "combined_image_path": combined_image_path,
        "targets": targets,
        "match_threshold": match_threshold,
    }
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "app.worker.run_processing_job"],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=settings.processing_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "OCR processing timed out after "
            f"{settings.processing_timeout_seconds} seconds. "
            "Verify that PaddleOCR model files are installed locally before retrying."
        ) from exc

    response = _parse_job_response(completed.stdout)
    if completed.returncode != 0:
        error_message = response.get("error") if response else None
        stderr = completed.stderr.strip()
        if error_message:
            raise RuntimeError(str(error_message))
        if stderr:
            raise RuntimeError(stderr)
        raise RuntimeError(f"OCR worker exited with code {completed.returncode}")

    if not response:
        raise RuntimeError("OCR worker returned no result payload")
    if "error" in response:
        raise RuntimeError(str(response["error"]))
    return response


def run_ocr_pipeline(
    *,
    combined_image_path: str,
    targets: list[dict[str, object]],
    match_threshold: int,
) -> dict[str, object]:
    image = load_processed_image(combined_image_path)
    processed_image = preprocess_image(_encode_image_bytes(image))
    engine = get_ocr_engine()
    ocr_boxes = _extract_text_with_rotation_fallbacks(
        engine,
        processed_image,
        warning_image=image if _has_warning_target(targets) else None,
        front_label_image=image if _has_front_label_text_target(targets) else None,
    )
    matches = match_targets(
        ocr_boxes,
        [str(item["expected_text"]) for item in targets],
        match_threshold=match_threshold,
        policies=[
            FIELD_MATCH_POLICIES.get(
                str(item["field"]),
                MatchPolicy(field=str(item["field"])),
            )
            for item in targets
        ],
    )
    match_results = []
    for target_meta, match in zip(targets, matches):
        match_results.append(
            {
                "field": target_meta["field"],
                "label": target_meta["label"],
                "required": target_meta["required"],
                "expected_text": target_meta["expected_text"],
                "matched": match.found,
                "found": match.found,
                "matched_text": match.matched_text,
                "closest_text": match.closest_text,
                "fuzzy_score": match.score,
                "ocr_confidence": match.ocr_confidence,
                "combined_confidence": match.combined_confidence,
                "bbox": match.bbox,
                "candidate_source": match.candidate_source,
                "feedback_message": _feedback_message(str(target_meta["field"]), match.found, match.score),
            }
        )

    approved = all(result["matched"] for result in match_results if result["required"])
    return {
        "match_results": match_results,
        "approved": approved,
    }


def get_ocr_engine() -> PaddleOCREngine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = PaddleOCREngine()
    return _engine


def _extract_text_with_rotation_fallbacks(
    engine: PaddleOCREngine,
    image,  # type: ignore[no-untyped-def]
    *,
    warning_image=None,  # type: ignore[no-untyped-def]
    front_label_image=None,  # type: ignore[no-untyped-def]
) -> list[OCRTextBox]:
    boxes = list(engine.extract_text(image))

    height, width = image.shape[:2]
    clockwise = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    boxes.extend(
        _map_rotated_boxes(
            engine.extract_text(clockwise),
            width=width,
            height=height,
            rotation="clockwise",
        )
    )

    counterclockwise = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    boxes.extend(
        _map_rotated_boxes(
            engine.extract_text(counterclockwise),
            width=width,
            height=height,
            rotation="counterclockwise",
        )
    )
    if warning_image is not None:
        boxes.extend(_extract_warning_crop_text(engine, warning_image))
    if front_label_image is not None:
        boxes.extend(_extract_front_label_crop_text(engine, front_label_image))
    return boxes


def _extract_warning_crop_text(
    engine: PaddleOCREngine,
    image,  # type: ignore[no-untyped-def]
) -> list[OCRTextBox]:
    height, width = image.shape[:2]
    crop_specs = [
        (0.59, 0.60, 0.96, 0.70, 3.0),
        (0.61, 0.62, 0.94, 0.73, 3.0),
        (0.61, 0.63, 0.94, 0.81, 3.0),
        (0.68, 0.82, 1.00, 0.995, 4.0),
        (0.65, 0.78, 1.00, 0.995, 4.0),
    ]
    rotated_crop_specs = [
        (0.87, 0.12, 0.94, 0.58, 6.0),
        (0.80, 0.10, 0.97, 0.58, 4.0),
    ]
    boxes: list[OCRTextBox] = []
    for left_ratio, top_ratio, right_ratio, bottom_ratio, scale in crop_specs:
        left = int(width * left_ratio)
        top = int(height * top_ratio)
        right = min(int(width * right_ratio), width)
        bottom = min(int(height * bottom_ratio), height)
        if right <= left or bottom <= top:
            continue
        crop = image[top:bottom, left:right]
        scaled = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        mapped_boxes = _map_scaled_crop_boxes(
            engine.extract_text(scaled),
            left=left,
            top=top,
            scale=scale,
        )
        boxes.extend(mapped_boxes)
        joined_box = _joined_ocr_text_box(mapped_boxes)
        if joined_box is not None:
            boxes.append(joined_box)
    for left_ratio, top_ratio, right_ratio, bottom_ratio, scale in rotated_crop_specs:
        left = int(width * left_ratio)
        top = int(height * top_ratio)
        right = min(int(width * right_ratio), width)
        bottom = min(int(height * bottom_ratio), height)
        if right <= left or bottom <= top:
            continue
        crop = image[top:bottom, left:right]
        rotated = cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE)
        scaled = cv2.resize(rotated, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        mapped_boxes = _map_clockwise_scaled_crop_boxes(
            engine.extract_text(scaled),
            left=left,
            top=top,
            crop_height=bottom - top,
            scale=scale,
        )
        boxes.extend(mapped_boxes)
        joined_box = _joined_ocr_text_box(mapped_boxes)
        if joined_box is not None:
            boxes.append(joined_box)
    return boxes


def _extract_front_label_crop_text(
    engine: PaddleOCREngine,
    image,  # type: ignore[no-untyped-def]
) -> list[OCRTextBox]:
    height, width = image.shape[:2]
    crop_specs = [
        (0.09, 0.905, 0.43, 0.975, 8.0),
        (0.10, 0.918, 0.42, 0.965, 10.0),
    ]
    boxes: list[OCRTextBox] = []
    for left_ratio, top_ratio, right_ratio, bottom_ratio, scale in crop_specs:
        left = int(width * left_ratio)
        top = int(height * top_ratio)
        right = min(int(width * right_ratio), width)
        bottom = min(int(height * bottom_ratio), height)
        if right <= left or bottom <= top:
            continue
        crop = image[top:bottom, left:right]
        scaled = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        for variant in _low_contrast_text_variants(scaled):
            boxes.extend(
                _map_scaled_crop_boxes(
                    engine.extract_text(variant),
                    left=left,
                    top=top,
                    scale=scale,
                )
            )
    return boxes


def _low_contrast_text_variants(image):  # type: ignore[no-untyped-def]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)
    blur = cv2.GaussianBlur(clahe, (0, 0), 1.0)
    sharp = cv2.addWeighted(clahe, 1.8, blur, -0.8, 0)
    return [
        cv2.cvtColor(clahe, cv2.COLOR_GRAY2BGR),
        cv2.cvtColor(sharp, cv2.COLOR_GRAY2BGR),
    ]


def _map_scaled_crop_boxes(
    boxes: list[OCRTextBox],
    *,
    left: int,
    top: int,
    scale: float,
) -> list[OCRTextBox]:
    return [
        OCRTextBox(
            text=box.text,
            confidence=box.confidence,
            bbox=[
                [left + point[0] / scale, top + point[1] / scale]
                for point in box.bbox
            ],
        )
        for box in boxes
    ]


def _joined_ocr_text_box(boxes: list[OCRTextBox]) -> OCRTextBox | None:
    if len(boxes) < 2:
        return None

    ordered = sorted(
        boxes,
        key=lambda box: (
            min(point[1] for point in box.bbox),
            min(point[0] for point in box.bbox),
        ),
    )
    confidence = sum(box.confidence for box in ordered) / len(ordered)
    points = [point for box in ordered for point in box.bbox]
    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    return OCRTextBox(
        text=" ".join(box.text for box in ordered),
        confidence=confidence,
        bbox=[[min_x, min_y], [max_x, min_y], [max_x, max_y], [min_x, max_y]],
    )


def _map_clockwise_scaled_crop_boxes(
    boxes: list[OCRTextBox],
    *,
    left: int,
    top: int,
    crop_height: int,
    scale: float,
) -> list[OCRTextBox]:
    return [
        OCRTextBox(
            text=box.text,
            confidence=box.confidence,
            bbox=[
                [left + point[1] / scale, top + crop_height - (point[0] / scale)]
                for point in box.bbox
            ],
        )
        for box in boxes
    ]


def _map_rotated_boxes(
    boxes: list[OCRTextBox],
    *,
    width: int,
    height: int,
    rotation: str,
) -> list[OCRTextBox]:
    return [
        OCRTextBox(
            text=box.text,
            confidence=box.confidence,
            bbox=_map_rotated_bbox(box.bbox, width=width, height=height, rotation=rotation),
        )
        for box in boxes
    ]


def _map_rotated_bbox(
    bbox: BBox,
    *,
    width: int,
    height: int,
    rotation: str,
) -> BBox:
    if rotation == "clockwise":
        return [[point[1], float(height) - point[0]] for point in bbox]
    if rotation == "counterclockwise":
        return [[float(width) - point[1], point[0]] for point in bbox]
    raise ValueError(f"Unsupported rotation: {rotation}")


def _targets_for_submission(submission: Submission) -> list[dict[str, object]]:
    targets: list[dict[str, object]] = []
    for spec in FIELD_SPECS:
        expected = getattr(submission, spec["attribute"])
        if spec["field"] in {"alcohol", "origin", "appellation"} and not expected:
            continue
        required = bool(spec["required"])
        if spec["field"] in {"origin", "appellation"}:
            required = True
        targets.append(
            {
                "field": spec["field"],
                "label": spec["label"],
                "expected_text": expected,
                "required": required,
            }
        )
    return targets


def _has_warning_target(targets: list[dict[str, object]]) -> bool:
    return any(str(target.get("field")) == "warning" for target in targets)


def _has_front_label_text_target(targets: list[dict[str, object]]) -> bool:
    return any(str(target.get("field")) in {"origin", "appellation"} for target in targets)


def _feedback_message(field_name: str, found: bool, score: float) -> str:
    if found:
        return f"Matched {field_name} with score {score:.2f}"
    return f"Did not find a confident match for {field_name}"
def _encode_image_bytes(image) -> bytes:  # type: ignore[no-untyped-def]
    success, encoded = cv2.imencode(".png", image)
    if not success:
        raise ValueError("Failed to encode processed image for OCR")
    return encoded.tobytes()


def _parse_job_response(stdout: str) -> dict[str, object]:
    payload = stdout.strip()
    if not payload:
        return {}

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"OCR worker returned invalid JSON: {payload}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("OCR worker returned an unexpected payload shape")
    return parsed
