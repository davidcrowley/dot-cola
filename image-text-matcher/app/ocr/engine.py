from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np

from app.models import OCRTextBox


class PaddleOCREngine:
    name = "paddleocr"

    def __init__(self) -> None:
        try:
            from paddleocr import PaddleOCR
            from paddleocr.paddleocr import BASE_DIR, confirm_model_dir_url, get_model_config, parse_lang
        except ImportError as exc:
            raise RuntimeError(_build_paddle_import_error(exc)) from exc

        det_model_dir, rec_model_dir, cls_model_dir = _resolve_model_directories(
            base_dir=BASE_DIR,
            confirm_model_dir_url=confirm_model_dir_url,
            get_model_config=get_model_config,
            parse_lang=parse_lang,
        )

        # PaddleOCR constructor arguments vary across versions. These options
        # are supported by the common 2.x line and keep OCR local.
        try:
            self._ocr = PaddleOCR(
                use_angle_cls=True,
                lang="en",
                show_log=False,
                det_model_dir=det_model_dir,
                rec_model_dir=rec_model_dir,
                cls_model_dir=cls_model_dir,
            )
        except RuntimeError as exc:
            raise RuntimeError(_build_paddle_runtime_error(exc)) from exc

        missing_models = _missing_model_artifacts([det_model_dir, rec_model_dir, cls_model_dir])
        if missing_models:
            raise RuntimeError(_build_missing_model_error(missing_models))

    def extract_text(self, image: np.ndarray) -> list[OCRTextBox]:
        raw = self._ocr.ocr(image, cls=True)
        return _parse_paddle_result(raw)


def _parse_paddle_result(raw: Any) -> list[OCRTextBox]:
    """Normalize PaddleOCR outputs into OCRTextBox objects.

    PaddleOCR has returned both [line, ...] and [[line, ...]] shapes depending
    on version and invocation style. Each line is usually:
    [bbox, (text, confidence)].
    """
    if not raw:
        return []

    lines = raw
    if isinstance(raw, list) and len(raw) == 1 and isinstance(raw[0], list):
        first = raw[0]
        if not first or _looks_like_paddle_line(first[0]):
            lines = first

    boxes: list[OCRTextBox] = []
    for line in lines:
        if not _looks_like_paddle_line(line):
            continue
        bbox_raw, text_info = line[0], line[1]
        text = str(text_info[0])
        confidence = float(text_info[1])
        bbox = [[float(point[0]), float(point[1])] for point in bbox_raw]
        boxes.append(OCRTextBox(text=text, confidence=confidence, bbox=bbox))
    return boxes


def _looks_like_paddle_line(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) >= 2
        and isinstance(value[0], (list, tuple))
        and isinstance(value[1], (list, tuple))
        and len(value[1]) >= 2
    )


def _build_paddle_import_error(exc: ImportError) -> str:
    missing_name = getattr(exc, "name", None)
    if missing_name == "paddleocr":
        return "PaddleOCR is not installed. Install requirements.txt before starting the app."

    if missing_name:
        return (
            "PaddleOCR failed to import because dependency "
            f"'{missing_name}' is missing. Reinstall requirements.txt or install "
            f"'{missing_name}' in the active virtualenv."
        )

    return f"PaddleOCR failed to import: {exc}"


def _build_paddle_runtime_error(exc: RuntimeError) -> str:
    message = str(exc)
    if "Download from" in message and "failed" in message:
        return (
            "PaddleOCR model download failed. Start the app once with network access "
            "to populate the local model cache, or pre-bundle the PaddleOCR model files "
            "for offline use."
        )

    return message


def _resolve_model_directories(*, base_dir: str, confirm_model_dir_url, get_model_config, parse_lang) -> tuple[str, str, str]:  # type: ignore[no-untyped-def]
    lang, det_lang = parse_lang("en")
    det_model_config = get_model_config("OCR", "PP-OCRv4", "det", det_lang)
    rec_model_config = get_model_config("OCR", "PP-OCRv4", "rec", lang)
    cls_model_config = get_model_config("OCR", "PP-OCRv4", "cls", "ch")

    det_model_dir, _ = confirm_model_dir_url(
        None,
        os.path.join(base_dir, "whl", "det", det_lang),
        det_model_config["url"],
    )
    rec_model_dir, _ = confirm_model_dir_url(
        None,
        os.path.join(base_dir, "whl", "rec", lang),
        rec_model_config["url"],
    )
    cls_model_dir, _ = confirm_model_dir_url(
        None,
        os.path.join(base_dir, "whl", "cls"),
        cls_model_config["url"],
    )
    return det_model_dir, rec_model_dir, cls_model_dir


def _missing_model_artifacts(model_dirs: list[str]) -> list[str]:
    missing: list[str] = []
    for model_dir in model_dirs:
        path = Path(model_dir)
        if not (path / "inference.pdmodel").exists() or not (path / "inference.pdiparams").exists():
            missing.append(str(path))
    return missing


def _build_missing_model_error(missing_models: list[str]) -> str:
    locations = ", ".join(missing_models)
    return (
        "PaddleOCR model files are missing. Expected local model artifacts in "
        f"{locations}. Start the app with network access to populate ~/.paddleocr, "
        "or pre-bundle those model directories before enabling queue processing."
    )
