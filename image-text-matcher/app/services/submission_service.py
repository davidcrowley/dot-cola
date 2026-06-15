from __future__ import annotations

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import DEFAULT_GOVERNMENT_WARNING
from app.db.models import Submission
from app.schemas.submission import SubmissionBase, SubmissionCreate, SubmissionUpdate
from app.services.queue_service import create_queue_item


def create_submissions(
    db: Session,
    payload: SubmissionCreate | list[SubmissionCreate],
) -> Submission | list[Submission]:
    if isinstance(payload, list):
        created = [_create_submission_record(db, item) for item in payload]
        return created
    return _create_submission_record(db, payload)


def list_submissions(db: Session, limit: int = 100, offset: int = 0) -> list[Submission]:
    stmt = select(Submission).order_by(Submission.created.desc(), Submission.id.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt))


def get_submission(db: Session, submission_id: int, include_results: bool = False) -> Submission:
    stmt = select(Submission).where(Submission.id == submission_id)
    if include_results:
        stmt = stmt.options(selectinload(Submission.process_results))
    submission = db.scalars(stmt).first()
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    return submission


def update_submission(db: Session, submission_id: int, payload: SubmissionUpdate) -> Submission:
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    data = payload.model_dump(exclude_unset=True, by_alias=False)
    data.pop("created", None)
    data.pop("warning", None)
    merged_data = {
        "brand": submission.brand,
        "class_type": submission.class_type,
        "address": submission.address,
        "net_contents": submission.net_contents,
        "alcohol": submission.alcohol,
        "origin": submission.origin,
        "appellation": submission.appellation,
        "warning": DEFAULT_GOVERNMENT_WARNING,
        "category": submission.category,
        "images": submission.images,
    }
    merged_data.update(data)
    try:
        SubmissionBase.model_validate(merged_data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    for field_name, value in data.items():
        setattr(submission, field_name, value)
    submission.warning = DEFAULT_GOVERNMENT_WARNING
    db.commit()
    db.refresh(submission)
    return submission


def delete_submission(db: Session, submission_id: int) -> None:
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    db.delete(submission)
    db.commit()


def _create_submission_record(db: Session, payload: SubmissionCreate) -> Submission:
    data = payload.model_dump(by_alias=False)
    data["warning"] = DEFAULT_GOVERNMENT_WARNING
    submission = Submission(**data)
    db.add(submission)
    db.commit()
    db.refresh(submission)
    create_queue_item(db, submission.id)
    db.refresh(submission)
    return submission
