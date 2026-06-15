from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.serializers import serialize_process_result
from app.auth import require_authenticated
from app.config import get_settings
from app.db.models import ProcessResult
from app.db.session import get_db
from app.schemas.process_result import ProcessResultRead


router = APIRouter(tags=["process-results"])


@router.get("/process-results", response_model=list[ProcessResultRead])
def list_all_process_results(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: None = Depends(require_authenticated),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    stmt = select(ProcessResult).order_by(ProcessResult.created.desc(), ProcessResult.id.desc()).limit(limit).offset(offset)
    return [serialize_process_result(item) for item in db.scalars(stmt)]


@router.get("/submissions/{submission_id}/process-results", response_model=list[ProcessResultRead])
def list_process_results(
    submission_id: int,
    _: None = Depends(require_authenticated),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    stmt = select(ProcessResult).where(ProcessResult.submission_id == submission_id).order_by(ProcessResult.created.desc())
    return [serialize_process_result(item) for item in db.scalars(stmt)]


@router.get("/process-results/{process_result_id}", response_model=ProcessResultRead)
def get_process_result(
    process_result_id: int,
    _: None = Depends(require_authenticated),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    process_result = db.get(ProcessResult, process_result_id)
    if process_result is None:
        raise HTTPException(status_code=404, detail="ProcessResult not found")
    return serialize_process_result(process_result)


@router.get("/process-results/{process_result_id}/image")
def get_process_result_image(
    process_result_id: int,
    _: None = Depends(require_authenticated),
    db: Session = Depends(get_db),
) -> FileResponse:
    process_result = db.get(ProcessResult, process_result_id)
    if process_result is None:
        raise HTTPException(status_code=404, detail="ProcessResult not found")
    image_path = _resolve_processed_image_path(process_result.combined_image)
    if not image_path.exists() or not image_path.is_file():
        raise HTTPException(status_code=404, detail="Processed image not found")
    return FileResponse(image_path)


@router.delete("/process-results/{process_result_id}", status_code=204)
def delete_process_result(
    process_result_id: int,
    _: None = Depends(require_authenticated),
    db: Session = Depends(get_db),
) -> Response:
    process_result = db.get(ProcessResult, process_result_id)
    if process_result is None:
        raise HTTPException(status_code=404, detail="ProcessResult not found")
    db.delete(process_result)
    db.commit()
    return Response(status_code=204)

def _resolve_processed_image_path(image_path: str) -> Path:
    processed_dir = Path(get_settings().processed_image_dir).resolve()
    candidate = Path(image_path)
    if not candidate.is_absolute():
        candidate = processed_dir / candidate
    candidate = candidate.resolve()
    if candidate != processed_dir and processed_dir not in candidate.parents:
        raise HTTPException(status_code=400, detail="Invalid processed image path")
    return candidate
