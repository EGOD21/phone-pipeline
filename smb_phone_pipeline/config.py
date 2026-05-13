from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    yp_api_base_url: str | None
    yp_api_key: str | None
    yp_api_timeout_seconds: int
    yp_authorizes_automated_extraction: bool
    yp_search_url_template: str | None


def load_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL", "postgresql://localhost/smb_phone_pipeline")
    timeout = int(os.getenv("YP_API_TIMEOUT_SECONDS", "10"))
    return Settings(
        database_url=database_url,
        yp_api_base_url=os.getenv("YP_API_BASE_URL") or None,
        yp_api_key=os.getenv("YP_API_KEY") or None,
        yp_api_timeout_seconds=timeout,
        yp_authorizes_automated_extraction=os.getenv(
            "YP_AUTHORIZES_AUTOMATED_EXTRACTION", "false"
        ).lower()
        in {"1", "true", "yes"},
        yp_search_url_template=os.getenv("YP_SEARCH_URL_TEMPLATE") or None,
    )
