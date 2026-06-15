from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.serializers import serialize_submission
from app.auth import require_authenticated
from app.db.session import get_db
from app.schemas.submission import SubmissionCreate, SubmissionRead, SubmissionUpdate
from app.services.submission_service import create_submissions, delete_submission, get_submission, list_submissions, update_submission


router = APIRouter(tags=["submissions"])


@router.post("/submissions", response_model=SubmissionRead | list[SubmissionRead], status_code=201)
def create_submission(
    payload: SubmissionCreate | list[SubmissionCreate],
    _: None = Depends(require_authenticated),
    db: Session = Depends(get_db),
):
    created = create_submissions(db, payload)
    if isinstance(created, list):
        return [serialize_submission(item) for item in created]
    return serialize_submission(created)


@router.get("/submissions", response_model=list[SubmissionRead])
def get_submissions(
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    _: None = Depends(require_authenticated),
    db: Session = Depends(get_db),
):
    return [serialize_submission(item) for item in list_submissions(db, limit=limit, offset=offset)]


@router.get("/submissions/{submission_id}", response_model=SubmissionRead)
def read_submission(
    submission_id: int,
    include_results: bool = False,
    _: None = Depends(require_authenticated),
    db: Session = Depends(get_db),
):
    submission = get_submission(db, submission_id, include_results=include_results)
    return serialize_submission(submission, include_results=include_results)


@router.patch("/submissions/{submission_id}", response_model=SubmissionRead)
def patch_submission(
    submission_id: int,
    payload: SubmissionUpdate,
    _: None = Depends(require_authenticated),
    db: Session = Depends(get_db),
):
    submission = update_submission(db, submission_id, payload)
    return serialize_submission(submission)


@router.delete("/submissions/{submission_id}", status_code=204)
def remove_submission(
    submission_id: int,
    _: None = Depends(require_authenticated),
    db: Session = Depends(get_db),
) -> Response:
    delete_submission(db, submission_id)
    return Response(status_code=204)
