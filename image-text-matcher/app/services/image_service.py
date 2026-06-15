from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil

import cv2
import numpy as np

from app.config import get_settings


def resolve_image_path(image_path: str) -> Path:
    settings = get_settings()
    base_dir = Path(settings.image_base_dir)
    candidate = Path(image_path)
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    candidate = candidate.resolve()
    if not candidate.exists():
        raise FileNotFoundError(f"Image path does not exist: {image_path}")
    return candidate


def build_submission_image(image_path: str, submission_id: int, queue_item_id: int) -> str:
    resolved = resolve_image_path(image_path)
    output_dir = Path(get_settings().processed_image_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    output_path = output_dir / f"submission_{submission_id}_queue_{queue_item_id}_{timestamp}.png"

    if resolved.suffix.lower() == ".png":
        shutil.copy2(resolved, output_path)
        return str(output_path)

    image = _read_image(resolved)
    _write_image(output_path, image)
    return str(output_path)


def load_processed_image(image_path: str) -> np.ndarray:
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Failed to read image: {image_path}")
    return image


def _read_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"Failed to read image: {path}")
    return image
def _write_image(path: Path, image: np.ndarray) -> None:
    if not cv2.imwrite(str(path), image):
        raise ValueError(f"Failed to write processed image: {path}")
