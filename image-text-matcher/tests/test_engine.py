from __future__ import annotations

import builtins
import sys
import types
from pathlib import Path

import pytest

from app.ocr.engine import PaddleOCREngine, _build_paddle_runtime_error


def test_engine_reports_missing_paddleocr_package(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake_import(name: str, globals=None, locals=None, fromlist=(), level: int = 0):
        if name == "paddleocr":
            raise ModuleNotFoundError("No module named 'paddleocr'", name="paddleocr")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="PaddleOCR is not installed"):
        PaddleOCREngine()


def test_engine_reports_missing_transitive_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake_import(name: str, globals=None, locals=None, fromlist=(), level: int = 0):
        if name == "paddleocr":
            raise ModuleNotFoundError("No module named 'setuptools'", name="setuptools")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="dependency 'setuptools' is missing"):
        PaddleOCREngine()


def test_runtime_error_explains_model_download_failure() -> None:
    error = RuntimeError("Download from https://example.com/model.tar failed. Retry limit reached")

    message = _build_paddle_runtime_error(error)

    assert "model download failed" in message
    assert "network access" in message


def test_engine_allows_paddleocr_to_populate_missing_model_dirs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model_dirs = {
        "det": tmp_path / "det",
        "rec": tmp_path / "rec",
        "cls": tmp_path / "cls",
    }
    constructor_calls: list[dict[str, str]] = []

    class FakePaddleOCR:
        def __init__(self, **kwargs) -> None:
            constructor_calls.append(kwargs)
            for key in ("det_model_dir", "rec_model_dir", "cls_model_dir"):
                model_dir = Path(kwargs[key])
                model_dir.mkdir(parents=True)
                (model_dir / "inference.pdmodel").write_text("model")
                (model_dir / "inference.pdiparams").write_text("params")

    def fake_confirm_model_dir_url(_model_dir, default_model_dir: str, url: str):
        for key, model_dir in model_dirs.items():
            if key in url:
                return str(model_dir), url
        return default_model_dir, url

    def fake_get_model_config(_category: str, _version: str, model_type: str, _lang: str):
        return {"url": f"https://example.com/{model_type}.tar"}

    paddleocr_package = types.ModuleType("paddleocr")
    paddleocr_package.PaddleOCR = FakePaddleOCR

    paddleocr_module = types.ModuleType("paddleocr.paddleocr")
    paddleocr_module.BASE_DIR = str(tmp_path)
    paddleocr_module.confirm_model_dir_url = fake_confirm_model_dir_url
    paddleocr_module.get_model_config = fake_get_model_config
    paddleocr_module.parse_lang = lambda _lang: ("en", "en")

    monkeypatch.setitem(sys.modules, "paddleocr", paddleocr_package)
    monkeypatch.setitem(sys.modules, "paddleocr.paddleocr", paddleocr_module)

    PaddleOCREngine()

    assert len(constructor_calls) == 1
    assert constructor_calls[0]["det_model_dir"] == str(model_dirs["det"])
