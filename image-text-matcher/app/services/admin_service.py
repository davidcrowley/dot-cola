from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import AppSetting


PROCESSING_ENABLED_KEY = "processing_enabled"
WorkerHealthProvider = Callable[[], dict[str, object]]
_worker_health_provider: WorkerHealthProvider | None = None


def is_processing_enabled(db: Session) -> bool:
    setting = db.get(AppSetting, PROCESSING_ENABLED_KEY)
    if setting is None:
        return get_settings().processing_enabled_default
    return setting.value.lower() == "true"


def set_processing_enabled(db: Session, enabled: bool) -> bool:
    setting = db.get(AppSetting, PROCESSING_ENABLED_KEY)
    if setting is None:
        setting = AppSetting(key=PROCESSING_ENABLED_KEY, value="true" if enabled else "false")
        db.add(setting)
    else:
        setting.value = "true" if enabled else "false"
    db.commit()
    return enabled


def get_processing_status(db: Session) -> dict[str, object]:
    enabled = is_processing_enabled(db)
    return {
        "processing_enabled": enabled,
        "status": "enabled" if enabled else "paused",
    }


def set_worker_health_provider(provider: WorkerHealthProvider | None) -> None:
    global _worker_health_provider
    _worker_health_provider = provider


def get_worker_health() -> dict[str, object]:
    if _worker_health_provider is not None:
        return _worker_health_provider()

    return {
        "worker_available": False,
        "worker_status": "offline",
        "worker_count": 0,
    }
