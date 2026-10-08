"""Conversation identity and SQLite-backed chat history operations."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

try:  # Supports backend-directory Uvicorn and project-root test imports.
    from controllers.database_controller import DatabaseController
except ModuleNotFoundError:  # pragma: no cover - depends on launch directory
    from backend.controllers.database_controller import DatabaseController


class ConversationValidationError(ValueError):
    """A conversation identifier or history event is invalid."""


class ConversationPersistenceError(RuntimeError):
    """Conversation history could not be stored or loaded safely."""


class ConversationController:
    """Own conversation IDs and history writes outside the hotel read query."""

    def __init__(self, database_controller: DatabaseController) -> None:
        self._database = database_controller

    @staticmethod
    def normalize_id(conversation_id: str | None) -> str:
        """Accept a UUID or create one when a new conversation starts."""
        if conversation_id is None or not conversation_id.strip():
            return str(uuid4())
        try:
            return str(UUID(conversation_id.strip()))
        except (AttributeError, ValueError):
            raise ConversationValidationError("Conversation ID must be a UUID.") from None

    def record(
        self,
        conversation_id: str,
        *,
        role: str,
        stage: str,
        content: str,
    ) -> dict[str, str]:
        """Store one safe user, model, SQL, retrieval, or error event."""
        normalized_id = self.normalize_id(conversation_id)
        if role not in {"user", "assistant", "system"}:
            raise ConversationValidationError("Conversation role is invalid.")
        if stage not in {
            "user_question",
            "sql_proposal",
            "executed_sql",
            "retrieved_records",
            "assistant_answer",
            "error",
        }:
            raise ConversationValidationError("Conversation stage is invalid.")
        if not isinstance(content, str) or not content.strip():
            raise ConversationValidationError("Conversation content cannot be empty.")
        timestamp = datetime.now(timezone.utc).isoformat()
        try:
            return self._database.append_conversation_message(
                message_id=str(uuid4()),
                conversation_id=normalized_id,
                timestamp=timestamp,
                role=role,
                stage=stage,
                content=content,
            )
        except Exception:
            raise ConversationPersistenceError(
                "Conversation history could not be saved."
            ) from None

    def history(self, conversation_id: str) -> list[dict[str, str]]:
        """Return labeled history for one UUID without exposing credentials."""
        normalized_id = self.normalize_id(conversation_id)
        try:
            return self._database.list_conversation_messages(normalized_id)
        except Exception:
            raise ConversationPersistenceError(
                "Conversation history could not be loaded."
            ) from None


__all__ = [
    "ConversationController",
    "ConversationPersistenceError",
    "ConversationValidationError",
]
