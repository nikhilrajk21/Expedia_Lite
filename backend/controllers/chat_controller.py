"""Backend-only OpenAI chat controller for the basic Expedia Lite assistant."""

from collections.abc import Callable
from typing import Any

from openai import OpenAI

try:  # Supports backend-directory Uvicorn and project-root test imports.
    from app.config import get_openai_api_key, get_openai_model
except ModuleNotFoundError:  # pragma: no cover - depends on launch directory
    from backend.app.config import get_openai_api_key, get_openai_model


REQUEST_TIMEOUT_SECONDS = 20.0
MAX_MESSAGE_LENGTH = 4000


class ChatValidationError(Exception):
    """Raised when a chat message is blank or too long."""


class ChatConfigurationError(Exception):
    """Raised when the backend-only OpenAI configuration is incomplete."""


class ChatProviderError(Exception):
    """Raised when the provider fails or returns unusable output."""


class ChatController:
    """Send one user message to the configured OpenAI model without persistence."""

    def __init__(
        self,
        api_key_getter: Callable[[], str | None] = get_openai_api_key,
        model_getter: Callable[[], str | None] = get_openai_model,
        client_factory: Callable[..., Any] = OpenAI,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self._api_key_getter = api_key_getter
        self._model_getter = model_getter
        self._client_factory = client_factory
        self._timeout = timeout

    def reply(self, message: str) -> dict[str, str]:
        """Return a sanitized assistant reply for one non-persistent message."""
        normalized_message = _validate_message(message)
        api_key = self._api_key_getter()
        model = self._model_getter()
        if not api_key or not model:
            raise ChatConfigurationError("Chat is not configured.")

        try:
            client = self._client_factory(
                api_key=api_key,
                timeout=self._timeout,
                max_retries=0,
            )
            response = client.responses.create(
                model=model,
                input=normalized_message,
            )
            reply = getattr(response, "output_text", None)
        except Exception:
            # Provider exception text can contain request details or credentials.
            raise ChatProviderError("Chat provider is unavailable.") from None

        if not isinstance(reply, str) or not reply.strip():
            raise ChatProviderError("Chat provider returned no usable response.")
        return {"reply": reply.strip()}


def _validate_message(message: str) -> str:
    """Trim a message and reject blank or unreasonably large input."""
    if not isinstance(message, str):
        raise ChatValidationError("Message must be text.")
    normalized_message = message.strip()
    if not normalized_message:
        raise ChatValidationError("Message cannot be empty.")
    if len(normalized_message) > MAX_MESSAGE_LENGTH:
        raise ChatValidationError("Message is too long.")
    return normalized_message
