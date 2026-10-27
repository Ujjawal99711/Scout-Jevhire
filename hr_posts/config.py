from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str = "https://api.connectsafely.ai"
    timeout_seconds: float = 90.0
    default_count: int = 20
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    typesafe_api_key: str = ""
    typesafe_base_url: str = "https://api.typesafe.ai"
    typesafe_timeout_seconds: float = 30.0
    jev_model: str = "jev-latest"
    jev_threshold: float = 0.75

    @classmethod
    def from_env(cls) -> Settings:
        api_key = os.getenv("CONNECTSAFELY_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("CONNECTSAFELY_API_KEY is not configured")
        return cls(
            api_key=api_key,
            base_url=os.getenv("CONNECTSAFELY_BASE_URL", "https://api.connectsafely.ai").rstrip(
                "/"
            ),
            timeout_seconds=float(os.getenv("CONNECTSAFELY_TIMEOUT_SECONDS", "90")),
            default_count=int(os.getenv("CONNECTSAFELY_DEFAULT_COUNT", "20")),
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            typesafe_api_key=os.getenv("TYPESAFE_API_KEY", "").strip(),
            typesafe_base_url=os.getenv("TYPESAFE_BASE_URL", "https://api.typesafe.ai").rstrip(
                "/"
            ),
            typesafe_timeout_seconds=float(os.getenv("TYPESAFE_TIMEOUT_SECONDS", "30")),
            jev_model=os.getenv("JEV_MODEL", "jev-latest"),
            jev_threshold=float(os.getenv("JEV_HIRING_THRESHOLD", "0.75")),
        )
