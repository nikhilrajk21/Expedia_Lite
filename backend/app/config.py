"""Backend-only environment configuration helpers."""

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENVIRONMENT_FILE = PROJECT_ROOT / ".env"

# Load local configuration once when the backend process starts.
load_dotenv(dotenv_path=ENVIRONMENT_FILE, override=False)


def is_geoapify_api_key_configured() -> bool:
    """Return whether a non-blank Geoapify key is available without exposing it."""
    return get_geoapify_api_key() is not None


def get_geoapify_api_key() -> str | None:
    """Return the configured backend-only Geoapify key, or ``None`` when blank."""
    value = os.getenv("GEOAPIFY_API_KEY", "").strip()
    return value or None


def get_openai_api_key() -> str | None:
    """Return the configured backend-only OpenAI key, or ``None`` when blank."""
    value = os.getenv("OPENAI_API_KEY", "").strip()
    return value or None


def get_openai_model() -> str | None:
    """Return the configured OpenAI model, or ``None`` when blank."""
    value = os.getenv("OPENAI_MODEL", "").strip()
    return value or None
