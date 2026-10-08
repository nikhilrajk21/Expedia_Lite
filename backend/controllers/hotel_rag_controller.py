"""Read-only, business-aware hotel assistant workflow.

The controller deliberately keeps SQL generation, validation, execution, and
answer generation out of the FastAPI route.  It only reads the existing
SQLite database and never writes hotel, location, or nightly records.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import OpenAI

try:  # Supports backend-directory Uvicorn and project-root test imports.
    from app.config import get_openai_api_key, get_openai_model
    from controllers.chat_controller import (
        ChatConfigurationError,
        ChatController,
        ChatProviderError,
        _validate_message,
    )
    from controllers.conversation_controller import (
        ConversationController,
    )
    from controllers.database_controller import DatabaseController
except ModuleNotFoundError:  # pragma: no cover - depends on launch directory
    from backend.app.config import get_openai_api_key, get_openai_model
    from backend.controllers.chat_controller import (
        ChatConfigurationError,
        ChatController,
        ChatProviderError,
        _validate_message,
    )
    from backend.controllers.conversation_controller import (
        ConversationController,
    )
    from backend.controllers.database_controller import DatabaseController


REQUEST_TIMEOUT_SECONDS = 20.0
QUERY_TIMEOUT_SECONDS = 0.5
MAX_ROWS = 50
THREE_CHEAPEST_LIMIT = 3
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUDIT_PATH = PROJECT_ROOT / "backend" / "logs" / "hotel_rag.jsonl"

APPROVED_COLUMNS: dict[str, frozenset[str]] = {
    "saved_hotels": frozenset({"hotel_id", "name", "address", "latitude", "longitude"}),
    "saved_hotel_locations": frozenset(
        {"hotel_id", "zip_code", "latitude", "longitude"}
    ),
    "demo_hotel_nights": frozenset(
        {"hotel_id", "stay_date", "nightly_rate_cents", "rooms_available"}
    ),
}
APPROVED_TABLES = frozenset(APPROVED_COLUMNS)
SAFE_FUNCTIONS = frozenset({"count", "min", "max", "avg", "sum", "coalesce", "lower", "round"})
FORBIDDEN_SQL_WORDS = re.compile(
    r"\b(?:insert|update|delete|drop|alter|pragma|attach|detach|replace|create|vacuum|reindex|trigger)\b",
    re.IGNORECASE,
)
TABLE_REFERENCE = re.compile(r"\b(?:from|join)\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
NAMED_PARAMETER = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")


class HotelRagValidationError(Exception):
    """The model proposed an unsafe or malformed query."""


class HotelRagConfigurationError(Exception):
    """The backend-only model configuration is incomplete."""


class HotelRagProviderError(Exception):
    """The provider returned unusable output or failed safely."""


class HotelRagExecutionError(Exception):
    """The read-only query could not be executed within its safety limits."""


@dataclass(frozen=True)
class SqlProposal:
    """The constrained JSON contract requested from the model."""

    kind: str
    sql: str | None
    params: dict[str, object]
    clarification: str | None = None


class RagAuditLogger:
    """Append sanitized, clearly labeled RAG records without credentials."""

    def __init__(self, path: Path = DEFAULT_AUDIT_PATH) -> None:
        self._path = path

    def record(self, label: str, payload: Mapping[str, object]) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "label": label,
            **dict(payload),
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as audit_file:
                audit_file.write(json.dumps(entry, ensure_ascii=True, default=str) + "\n")
        except OSError:
            # Auditing must never turn a safe read-only answer into a failure.
            return


class HotelRagController:
    """Generate, validate, execute, and explain one hotel read-only query."""

    def __init__(
        self,
        database_controller: DatabaseController,
        *,
        api_key_getter: Callable[[], str | None] = get_openai_api_key,
        model_getter: Callable[[], str | None] = get_openai_model,
        client_factory: Callable[..., Any] = OpenAI,
        conversation_controller: ConversationController | None = None,
        fallback_chat_controller: ChatController | None = None,
        audit_logger: RagAuditLogger | None = None,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
        query_timeout: float = QUERY_TIMEOUT_SECONDS,
        max_rows: int = MAX_ROWS,
    ) -> None:
        self._database = database_controller
        self._api_key_getter = api_key_getter
        self._model_getter = model_getter
        self._client_factory = client_factory
        self._conversation = conversation_controller or ConversationController(database_controller)
        self._fallback_chat = fallback_chat_controller or ChatController(
            api_key_getter=api_key_getter,
            model_getter=model_getter,
            client_factory=client_factory,
            timeout=timeout,
        )
        self._audit = audit_logger or RagAuditLogger()
        self._timeout = timeout
        self._query_timeout = query_timeout
        self._max_rows = max_rows

    def reply(
        self, message: str, conversation_id: str | None = None
    ) -> dict[str, object]:
        """Return a safe answer and persist labeled events for one conversation."""
        question = _validate_message(message)
        normalized_conversation_id = self._conversation.normalize_id(conversation_id)
        self._record_event(
            normalized_conversation_id,
            role="user",
            stage="user_question",
            content=question,
            audit_label="user_question",
            audit_payload={"content": question},
        )
        history = self._conversation.history(normalized_conversation_id)
        prior_history = history[:-1]
        api_key = self._api_key_getter()
        model = self._model_getter()
        if not api_key or not model:
            self._record_error(normalized_conversation_id, "configuration")
            raise HotelRagConfigurationError("Hotel assistant is not configured.")

        try:
            client = self._make_client(api_key)
            proposal = self._propose(client, model, question, prior_history)
        except HotelRagValidationError:
            self._record_error(normalized_conversation_id, "proposal_validation")
            raise
        except HotelRagProviderError:
            self._record_error(normalized_conversation_id, "provider")
            raise
        self._audit.record(
            "proposed_sql",
            {
                "conversation_id": normalized_conversation_id,
                "kind": proposal.kind,
                "sql": proposal.sql,
                "params": proposal.params,
                "clarification": proposal.clarification,
            },
        )
        self._record_event(
            normalized_conversation_id,
            role="assistant",
            stage="sql_proposal",
            content=json.dumps(
                {
                    "kind": proposal.kind,
                    "sql": proposal.sql,
                    "params": proposal.params,
                    "clarification": proposal.clarification,
                },
                ensure_ascii=True,
            ),
            audit_label=None,
        )

        if proposal.kind == "clarification":
            answer = proposal.clarification or "Please provide the ZIP code or stay date."
            self._record_assistant_answer(normalized_conversation_id, answer)
            return {"conversation_id": normalized_conversation_id, "reply": answer}

        if proposal.kind == "general":
            try:
                answer = self._fallback_chat.reply(question)["reply"]
            except ChatConfigurationError:
                self._record_error(normalized_conversation_id, "configuration")
                raise HotelRagConfigurationError("Hotel assistant is not configured.") from None
            except ChatProviderError:
                self._record_error(normalized_conversation_id, "provider")
                raise HotelRagProviderError("Chat provider is unavailable.") from None
            self._record_assistant_answer(normalized_conversation_id, answer)
            return {"conversation_id": normalized_conversation_id, "reply": answer}

        if proposal.sql is None:
            self._record_error(normalized_conversation_id, "query_validation")
            raise HotelRagValidationError("The assistant did not provide a query.")

        requested_limit = _requested_result_limit(question)
        effective_limit = min(self._max_rows, requested_limit or self._max_rows)
        try:
            rows = self._execute_read_only(
                proposal.sql,
                proposal.params,
                row_limit=effective_limit,
            )
        except HotelRagValidationError:
            self._record_error(normalized_conversation_id, "query_validation")
            raise
        except HotelRagExecutionError:
            self._record_error(normalized_conversation_id, "query_execution")
            raise

        self._audit.record(
            "executed_sql",
            {
                "conversation_id": normalized_conversation_id,
                "sql": proposal.sql,
                "params": proposal.params,
                "row_limit": effective_limit,
            },
        )
        self._record_event(
            normalized_conversation_id,
            role="system",
            stage="executed_sql",
            content=json.dumps(
                {"sql": proposal.sql, "params": proposal.params, "row_limit": effective_limit},
                ensure_ascii=True,
            ),
            audit_label=None,
        )
        self._audit.record(
            "retrieved_rows",
            {
                "conversation_id": normalized_conversation_id,
                "row_count": len(rows),
                "rows": rows if rows else [],
            },
        )
        self._record_event(
            normalized_conversation_id,
            role="system",
            stage="retrieved_records",
            content=json.dumps(
                {"row_count": len(rows), "rows": rows if rows else []},
                ensure_ascii=True,
                default=str,
            ),
            audit_label=None,
        )
        try:
            answer = self._final_answer(client, model, question, rows, prior_history)
        except HotelRagProviderError:
            self._record_error(normalized_conversation_id, "provider")
            raise
        if not rows:
            answer = "No matching saved hotel records were found for that question."
        else:
            answer = _ensure_consistent_answer(
                answer,
                rows,
                requested_limit=requested_limit,
            )
        self._record_assistant_answer(normalized_conversation_id, answer)
        return {"conversation_id": normalized_conversation_id, "reply": answer}

    def _record_event(
        self,
        conversation_id: str,
        *,
        role: str,
        stage: str,
        content: str,
        audit_label: str | None,
        audit_payload: Mapping[str, object] | None = None,
    ) -> None:
        self._conversation.record(
            conversation_id,
            role=role,
            stage=stage,
            content=content,
        )
        if audit_label:
            self._audit.record(
                audit_label,
                {"conversation_id": conversation_id, **dict(audit_payload or {})},
            )

    def _record_assistant_answer(self, conversation_id: str, answer: str) -> None:
        self._record_event(
            conversation_id,
            role="assistant",
            stage="assistant_answer",
            content=answer,
            audit_label="assistant_answer",
            audit_payload={"content": answer},
        )

    def _record_error(self, conversation_id: str, category: str) -> None:
        safe_content = json.dumps({"category": category}, ensure_ascii=True)
        self._record_event(
            conversation_id,
            role="system",
            stage="error",
            content=safe_content,
            audit_label="error",
            audit_payload={"category": category},
        )

    def _make_client(self, api_key: str) -> Any:
        try:
            return self._client_factory(
                api_key=api_key,
                timeout=self._timeout,
                max_retries=0,
            )
        except Exception:
            raise HotelRagProviderError("Chat provider is unavailable.") from None

    def _propose(
        self,
        client: Any,
        model: str,
        question: str,
        history: list[dict[str, str]],
    ) -> SqlProposal:
        try:
            response = client.responses.create(
                model=model,
                input=_proposal_prompt(question, history),
            )
            raw = getattr(response, "output_text", None)
            if not isinstance(raw, str) or not raw.strip():
                raise ValueError("empty proposal")
            return _parse_proposal(raw)
        except HotelRagValidationError:
            raise
        except Exception:
            raise HotelRagProviderError("Chat provider is unavailable.") from None

    def _execute_read_only(
        self,
        sql: str,
        params: Mapping[str, object],
        *,
        row_limit: int | None = None,
    ) -> list[dict[str, object]]:
        _validate_sql_text(sql, params)
        connection = self._database.open()
        try:
            connection.set_authorizer(_read_only_authorizer)
            deadline = time.monotonic() + self._query_timeout

            def stop_if_slow() -> int:
                return int(time.monotonic() >= deadline)

            connection.set_progress_handler(stop_if_slow, 1000)
            try:
                # Preparing a plan catches unknown tables/columns before any row read.
                connection.execute("EXPLAIN QUERY PLAN " + sql, dict(params)).fetchall()
                effective_limit = min(self._max_rows, row_limit or self._max_rows)
                limited_sql = f"SELECT * FROM ({sql}) AS hotel_rag_result LIMIT {effective_limit}"
                rows = connection.execute(limited_sql, dict(params)).fetchall()
            except sqlite3.OperationalError as error:
                if "interrupted" in str(error).lower():
                    raise HotelRagExecutionError("Hotel query timed out.") from None
                raise HotelRagValidationError("The proposed query was rejected.") from None
            except sqlite3.DatabaseError:
                raise HotelRagValidationError("The proposed query was rejected.") from None
            return [dict(row) for row in rows]
        finally:
            connection.close()

    def _final_answer(
        self,
        client: Any,
        model: str,
        question: str,
        rows: list[dict[str, object]],
        history: list[dict[str, str]],
    ) -> str:
        model_rows = []
        for row in rows:
            copy = dict(row)
            cents = copy.get("nightly_rate_cents")
            if isinstance(cents, (int, float)):
                copy["nightly_rate_dollars"] = round(float(cents) / 100, 2)
            model_rows.append(copy)
        try:
            response = client.responses.create(
                model=model,
                input=_answer_prompt(question, model_rows, history),
            )
            answer = getattr(response, "output_text", None)
        except Exception:
            raise HotelRagProviderError("Chat provider is unavailable.") from None
        if not isinstance(answer, str) or not answer.strip():
            raise HotelRagProviderError("Chat provider returned no usable response.")
        return answer.strip()


def _parse_proposal(raw: str) -> SqlProposal:
    text = raw.strip()
    if text.startswith("```") and text.endswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        payload = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        raise HotelRagValidationError("The assistant returned an invalid query proposal.") from None
    if not isinstance(payload, dict):
        raise HotelRagValidationError("The assistant returned an invalid query proposal.")
    kind = payload.get("kind")
    sql = payload.get("sql")
    params = payload.get("params", {})
    clarification = payload.get("message")
    if kind not in {"hotel_query", "general", "clarification"} or not isinstance(params, dict):
        raise HotelRagValidationError("The assistant returned an invalid query proposal.")
    if kind == "general":
        if sql is not None:
            raise HotelRagValidationError("The assistant returned an invalid query proposal.")
        return SqlProposal(kind=kind, sql=None, params={})
    if kind == "clarification":
        if sql is not None or not isinstance(clarification, str) or not clarification.strip():
            raise HotelRagValidationError("The assistant returned an invalid query proposal.")
        return SqlProposal(
            kind=kind,
            sql=None,
            params={},
            clarification=clarification.strip(),
        )
    if not isinstance(sql, str) or not sql.strip():
        raise HotelRagValidationError("The assistant returned an invalid query proposal.")
    return SqlProposal(kind=kind, sql=sql, params=params)


def _validate_sql_text(sql: str, params: Mapping[str, object]) -> None:
    text = sql.strip()
    if not text or not re.match(r"^select\b", text, re.IGNORECASE):
        raise HotelRagValidationError("Only one read-only SELECT is allowed.")
    if ";" in text or "--" in text or "/*" in text or "*/" in text:
        raise HotelRagValidationError("Multiple statements and SQL comments are not allowed.")
    if FORBIDDEN_SQL_WORDS.search(text):
        raise HotelRagValidationError("Only read-only hotel queries are allowed.")
    table_names = {match.group(1).lower() for match in TABLE_REFERENCE.finditer(text)}
    if not table_names or not table_names.issubset(APPROVED_TABLES):
        raise HotelRagValidationError("The query referenced an unapproved table.")
    if any(not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) for key in params):
        raise HotelRagValidationError("Query parameters are invalid.")
    placeholders = set(NAMED_PARAMETER.findall(text))
    if not placeholders.issubset(params):
        raise HotelRagValidationError("The query has missing parameters.")
    if any(not isinstance(value, (str, int, float, bool, type(None))) for value in params.values()):
        raise HotelRagValidationError("Query parameters are invalid.")


def _requested_result_limit(question: str) -> int | None:
    """Apply a narrow user-requested cap without weakening the global safety limit."""
    if "cheapest" in question.lower() and re.search(r"\b(?:three|3)\b", question, re.IGNORECASE):
        return THREE_CHEAPEST_LIMIT
    return None


def _read_only_authorizer(action: int, arg1: str | None, arg2: str | None, *_: object) -> int:
    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ):
        if action == sqlite3.SQLITE_READ:
            table = (arg1 or "").lower()
            column = (arg2 or "").lower()
            if table not in APPROVED_COLUMNS or column not in APPROVED_COLUMNS[table]:
                return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION:
        function_name = (arg2 or arg1 or "").lower()
        return sqlite3.SQLITE_OK if function_name in SAFE_FUNCTIONS else sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_DENY


def _proposal_prompt(question: str, history: list[dict[str, str]]) -> str:
    context = _history_context(history)
    return f"""You are the Expedia Lite hotel data assistant. Return JSON only.
Classify the question as a hotel_query, clarification, or general. For a
hotel_query, return:
{{"kind":"hotel_query","sql":"one SELECT statement","params":{{"name":"value"}}}}
For a clarification request return {{"kind":"clarification","sql":null,
"params":{{}},"message":"one clear question for the user"}}.
For a general question return {{"kind":"general","sql":null,"params":{{}}}}.

Approved tables and columns (and no others):
- saved_hotels(hotel_id, name, address, latitude, longitude)
- saved_hotel_locations(hotel_id, zip_code, latitude, longitude)
- demo_hotel_nights(hotel_id, stay_date, nightly_rate_cents, rooms_available)
Required relationships when needed:
saved_hotels.hotel_id = saved_hotel_locations.hotel_id
saved_hotels.hotel_id = demo_hotel_nights.hotel_id
Use named parameters, never interpolate user text. ZIP filters use
saved_hotel_locations.zip_code. Date filters use stay_date in YYYY-MM-DD.
Availability means rooms_available > 0. Order price questions by
demo_hotel_nights.nightly_rate_cents ASC. For a request for the three cheapest
saved hotels, include LIMIT 3; the controller enforces the same maximum. Only
one read-only SELECT is allowed.
No INSERT, UPDATE, DELETE, DROP, ALTER, PRAGMA, ATTACH, comments, or semicolons.
Use the prior conversation context for follow-ups. Carry forward a ZIP and
other necessary filters only when they are explicitly present in that context;
otherwise ask for clarification rather than guessing.

Prior conversation context:
{context}

Question: {question}
"""


def _answer_prompt(
    question: str,
    rows: list[dict[str, object]],
    history: list[dict[str, str]],
) -> str:
    return f"""Answer the Expedia Lite hotel question using only the retrieved rows below.
Do not invent hotels, dates, prices, room counts, addresses, or availability.
nightly_rate_cents is simulated classroom data; show it as dollars using the
provided nightly_rate_dollars value and label it simulated. A positive
rooms_available value means rooms are available. If the rows do not contain
the requested date, say that no saved record was found for that date.
If rows are present, do not say that no records were found.
Relevant prior context:
{_history_context(history)}
Question: {question}
Retrieved rows (JSON): {json.dumps(rows, ensure_ascii=True, default=str)}
"""


def _history_context(history: list[dict[str, str]]) -> str:
    """Keep prompts bounded while preserving labeled prior context."""
    if not history:
        return "(none)"
    entries = []
    for event in history[-12:]:
        content = event.get("content", "")
        entries.append(
            f"[{event.get('role', 'system')}/{event.get('stage', 'unknown')}] "
            + content[:3000]
        )
    return "\n".join(entries)


def _ensure_consistent_answer(
    answer: str,
    rows: list[dict[str, object]],
    *,
    requested_limit: int | None = None,
) -> str:
    """Replace contradictory model text with a deterministic row-only answer."""
    if requested_limit == THREE_CHEAPEST_LIMIT:
        return _format_row_only_answer(rows, requested_limit=requested_limit)
    contradiction = re.search(
        r"\b(?:no|none|not found|could not find)\b.{0,80}\b(?:record|hotel|result|match|saved|available)\b",
        answer,
        re.IGNORECASE | re.DOTALL,
    )
    if not contradiction:
        return answer
    return _format_row_only_answer(rows)


def _format_row_only_answer(
    rows: list[dict[str, object]],
    *,
    requested_limit: int | None = None,
) -> str:
    count = len(rows)
    if requested_limit:
        noun = "record" if count == 1 else "records"
        lines = [
            f"Found {count} matching saved hotel {noun} (requested up to "
            f"{requested_limit}; simulated classroom data):"
        ]
    else:
        lines = ["Matching saved hotel records (simulated classroom data):"]
    for row in rows:
        parts = []
        for key in ("name", "address", "zip_code", "stay_date", "rooms_available"):
            if row.get(key) is not None:
                parts.append(f"{key.replace('_', ' ')}: {row[key]}")
        cents = row.get("nightly_rate_cents")
        if isinstance(cents, (int, float)):
            parts.append(f"simulated nightly rate: ${float(cents) / 100:.2f}")
        lines.append("- " + "; ".join(parts))
    return "\n".join(lines)


__all__ = [
    "HotelRagConfigurationError",
    "HotelRagController",
    "HotelRagExecutionError",
    "HotelRagProviderError",
    "HotelRagValidationError",
    "RagAuditLogger",
    "SqlProposal",
]
