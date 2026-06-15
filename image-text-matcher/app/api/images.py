from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.auth import require_authenticated
from app.config import get_settings
from app.schemas.image import ImageFileRead
from app.utils.image_io import read_upload_bytes


SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


router = APIRouter(tags=["images"])


@router.get("/images", response_model=list[ImageFileRead])
def list_images(
    _: None = Depends(require_authenticated),
) -> list[dict[str, object]]:
    base_dir = _get_base_dir()
    image_files: list[dict[str, object]] = []
    for path in sorted(base_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            continue
        relative_path = path.relative_to(base_dir).as_posix()
        stat = path.stat()
        image_files.append(
            {
                "path": relative_path,
                "name": path.name,
                "sizeBytes": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                "previewUrl": f"/images/file?path={quote(relative_path, safe='')}",
            }
        )
    return image_files


@router.post("/images/upload")
async def upload_image(
    _: None = Depends(require_authenticated),
    image: UploadFile = File(...),
) -> dict[str, str]:
    contents = await read_upload_bytes(image)
    base_dir = _get_base_dir()
    upload_dir = base_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    filename = _build_upload_filename(image.filename)
    output_path = upload_dir / filename
    output_path.write_bytes(contents)

    relative_path = output_path.relative_to(base_dir).as_posix()
    return {"path": relative_path}


@router.get("/images/file")
def read_image_file(
    path: str = Query(...),
    _: None = Depends(require_authenticated),
) -> FileResponse:
    candidate = _resolve_relative_path(path)
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(candidate)


@router.delete("/images")
def delete_image_file(
    path: str = Query(...),
    _: None = Depends(require_authenticated),
) -> dict[str, str]:
    candidate = _resolve_relative_path(path)
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    candidate.unlink()
    return {"deleted": path}


def _get_base_dir() -> Path:
    return Path(get_settings().image_base_dir).resolve()


def _build_upload_filename(original_filename: str | None) -> str:
    source_name = Path((original_filename or "upload").replace("\\", "/")).name
    suffix = Path(source_name).suffix.lower()
    if not suffix:
        raise HTTPException(status_code=400, detail="Uploaded image must include a file extension")

    original_stem = Path(source_name).stem
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", original_stem).strip("._-")
    if not safe_stem:
        safe_stem = "upload"
    safe_stem = safe_stem[:80].rstrip("._-") or "upload"
    return f"{uuid4().hex}-{safe_stem}{suffix}"


def _resolve_relative_path(path: str) -> Path:
    if not path.strip():
        raise HTTPException(status_code=400, detail="Image path is required")

    base_dir = _get_base_dir()
    candidate = (base_dir / path).resolve()
    if candidate != base_dir and base_dir not in candidate.parents:
        raise HTTPException(status_code=400, detail="Invalid image path")
    return candidate
