from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.auth import router as auth_router
from app.api.admin import router as admin_router
from app.api.images import router as images_router
from app.api.process_results import router as process_results_router
from app.api.queue import router as queue_router
from app.api.submissions import router as submissions_router
from app.db.base import Base
from app.db.session import initialize_database
from app.matching.matcher import match_targets
from app.models import AnalyzeImageResponse
from app.ocr.preprocess import preprocess_image
from app.services.admin_service import set_worker_health_provider
from app.services.queue_service import set_queue_notifier
from app.services.processing_service import get_ocr_engine
from app.utils.image_io import read_upload_bytes
from app.worker.background import BackgroundQueueWorker


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    initialize_database(Base.metadata)
    worker = BackgroundQueueWorker()
    set_worker_health_provider(worker.health)
    set_queue_notifier(worker.wake)
    worker.start()
    try:
        yield
    finally:
        worker.stop()
        set_queue_notifier(None)
        set_worker_health_provider(None)


app = FastAPI(title="COLA Label Matcher", version="0.1.0", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(images_router)
app.include_router(submissions_router)
app.include_router(process_results_router)
app.include_router(queue_router)
app.include_router(admin_router)

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "ocr_engine": "paddleocr"}


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/gui")


@app.get("/gui")
def gui() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.post("/analyze-image", response_model=AnalyzeImageResponse)
async def analyze_image(
    image: UploadFile = File(...),
    targets_json: str = Form(...),
    match_threshold: int = Form(85),
) -> AnalyzeImageResponse:
    if not 0 <= match_threshold <= 100:
        raise HTTPException(status_code=400, detail="match_threshold must be between 0 and 100")

    targets = _parse_targets_json(targets_json)

    try:
        image_bytes = await read_upload_bytes(image)
        processed_image = preprocess_image(image_bytes)
        engine = get_ocr_engine()
        ocr_boxes = engine.extract_text(processed_image)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    matches = match_targets(ocr_boxes, targets, match_threshold=match_threshold)
    return AnalyzeImageResponse(
        filename=image.filename or "uploaded-image",
        ocr_engine=engine.name,
        match_threshold=match_threshold,
        matches=matches,
        raw_ocr_count=len(ocr_boxes),
    )


def _parse_targets_json(targets_json: str) -> list[str]:
    try:
        value: Any = json.loads(targets_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="targets_json must be valid JSON") from exc

    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise HTTPException(status_code=400, detail="targets_json must be a JSON array of strings")

    targets = [item.strip() for item in value if item.strip()]
    if not targets:
        raise HTTPException(status_code=400, detail="targets_json must include at least one string")

    return targets
