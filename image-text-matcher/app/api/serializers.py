from __future__ import annotations

from app.db.models import ProcessResult, Submission


def serialize_process_result(process_result: ProcessResult) -> dict[str, object]:
    return {
        "id": process_result.id,
        "submission_id": process_result.submission_id,
        "combined_image": process_result.combined_image,
        "combined_image_url": f"/process-results/{process_result.id}/image",
        "match_results": process_result.match_results,
        "approved": process_result.approved,
        "process_started": process_result.process_started,
        "process_completed": process_result.process_completed,
        "created": process_result.created,
        "status": process_result.status,
        "error_message": process_result.error_message,
    }


def serialize_submission(submission: Submission, *, include_results: bool = False) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": submission.id,
        "brand": submission.brand,
        "class_type": submission.class_type,
        "address": submission.address,
        "net_contents": submission.net_contents,
        "alcohol": submission.alcohol,
        "origin": submission.origin,
        "appellation": submission.appellation,
        "warning": submission.warning,
        "category": submission.category,
        "images": submission.images,
        "created": submission.created,
        "processed": submission.processed,
        "approved": submission.approved,
        "process_results": None,
    }
    if include_results:
        payload["process_results"] = [serialize_process_result(result) for result in submission.process_results]
    return payload
