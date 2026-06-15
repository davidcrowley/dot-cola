from __future__ import annotations

import os
from functools import lru_cache


DEFAULT_GOVERNMENT_WARNING = (
    "GOVERNMENT WARNING:(1) According to the Surgeon General, women should not drink "
    "alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car "
    "or operate machinery, and may cause health problems."
)


class Settings:
    def __init__(self) -> None:
        self.database_url = os.getenv(
            "DATABASE_URL",
            "sqlite:///./image_text_matcher.db",
        )
        self.match_threshold = int(os.getenv("MATCH_THRESHOLD", "85"))
        self.processing_enabled_default = _parse_bool(
            os.getenv("PROCESSING_ENABLED_DEFAULT", "true")
        )
        self.processed_image_dir = os.getenv("PROCESSED_IMAGE_DIR", "/data/processed")
        self.image_base_dir = os.getenv("IMAGE_BASE_DIR", "/data/images")
        self.queue_poll_interval_seconds = float(os.getenv("QUEUE_POLL_INTERVAL_SECONDS", "2"))
        self.processing_timeout_seconds = int(os.getenv("PROCESSING_TIMEOUT_SECONDS", "600"))
        self.processing_job_subprocess = _parse_bool(
            os.getenv("PROCESSING_JOB_SUBPROCESS", "false")
        )
        self.admin_username = os.getenv("ADMIN_USERNAME", "testadmin")
        self.admin_password = os.getenv("ADMIN_PASSWORD", "testadmin")
        self.api_key = os.getenv("API_KEY", "")
        self.session_secret_key = os.getenv("SESSION_SECRET_KEY", "change-me")


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
