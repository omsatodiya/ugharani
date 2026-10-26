"""Settings loaded from the environment / .env file."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    gnani_api_key: str
    gnani_base_url: str
    tts_model: str
    tts_voice: str
    language: str

    @property
    def auth_headers(self) -> dict[str, str]:
        return {"X-API-Key-ID": self.gnani_api_key}


def get_settings() -> Settings:
    key = os.getenv("GNANI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GNANI_API_KEY is not set. Copy .env.example to .env and fill it in.")
    return Settings(
        gnani_api_key=key,
        gnani_base_url=os.getenv("GNANI_BASE_URL", "https://api.vachana.ai").rstrip("/"),
        tts_model=os.getenv("TTS_MODEL", "timbre-v3.0"),
        tts_voice=os.getenv("TTS_VOICE", "Shivani"),
        language=os.getenv("LANGUAGE", "gu-IN"),
    )
