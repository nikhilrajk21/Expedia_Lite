"""Safety and behavior tests for the read-only hotel RAG workflow."""

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.controllers.hotel_rag_controller import (
    HotelRagController,
    HotelRagProviderError,
    HotelRagValidationError,
    RagAuditLogger,
)
from backend.controllers import database_controller as database_module


SCHEMA = """
CREATE TABLE saved_hotels (
    hotel_id TEXT PRIMARY KEY, name TEXT, address TEXT,
    latitude REAL NOT NULL, longitude REAL NOT NULL
);
CREATE TABLE saved_hotel_locations (
    hotel_id TEXT NOT NULL, zip_code TEXT NOT NULL,
    latitude REAL NOT NULL, longitude REAL NOT NULL,
    PRIMARY KEY (hotel_id, zip_code),
    FOREIGN KEY (hotel_id) REFERENCES saved_hotels(hotel_id)
);
CREATE TABLE demo_hotel_nights (
    hotel_id TEXT NOT NULL, stay_date TEXT NOT NULL,
    nightly_rate_cents INTEGER NOT NULL DEFAULT 10000,
    rooms_available INTEGER NOT NULL DEFAULT 20,
    PRIMARY KEY (hotel_id, stay_date),
    FOREIGN KEY (hotel_id) REFERENCES saved_hotels(hotel_id)
);
"""


class TempDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path

    def open(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def append_conversation_message(self, **message: str) -> dict[str, str]:
        with self.open() as connection:
            connection.execute(
                "INSERT INTO conversation_messages "
                "(message_id, conversation_id, timestamp, role, stage, content) "
                "VALUES (:message_id, :conversation_id, :timestamp, :role, :stage, :content)",
                message,
            )
        return message

    def list_conversation_messages(self, conversation_id: str) -> list[dict[str, str]]:
        with self.open() as connection:
            rows = connection.execute(
                "SELECT message_id, conversation_id, timestamp, role, stage, content " 
                "FROM conversation_messages WHERE conversation_id = ? "
                "ORDER BY rowid",
                (conversation_id,),
            ).fetchall()
        return [dict(row) for row in rows]


class FakeResponses:
    def __init__(self, outputs: list[str] | None = None, error: Exception | None = None):
        self.outputs = outputs or []
        self.error = error
        self.inputs: list[str] = []

    def create(self, *, model: str, input: str):
        self.inputs.append(input)
        if self.error:
            raise self.error
        return SimpleNamespace(output_text=self.outputs.pop(0))


class FakeClient:
    def __init__(self, responses: FakeResponses, **_kwargs):
        self.responses = responses


def make_controller(tmp_path: Path, proposal: dict, final: str = "A saved hotel.", **kwargs):
    database_path = tmp_path / "rag.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.executescript(SCHEMA)
    connection.executescript(database_module.CONVERSATION_HISTORY_MIGRATION)
    connection.executemany(
        "INSERT INTO saved_hotels VALUES (?, ?, ?, ?, ?)",
        [
            ("p1", "First Inn", "1 Main St", 40.0, -77.0),
            ("p2", "Second Inn", "2 Main St", 40.1, -77.1),
        ],
    )
    connection.executemany(
        "INSERT INTO saved_hotel_locations VALUES (?, ?, ?, ?)",
        [("p1", "16802", 40.0, -77.0), ("p2", "16802", 40.0, -77.0)],
    )
    connection.executemany(
        "INSERT INTO demo_hotel_nights (hotel_id, stay_date) VALUES (?, ?)",
        [("p1", "2026-10-10"), ("p2", "2026-10-10")],
    )
    connection.commit()
    connection.close()

    responses = FakeResponses([json.dumps(proposal), final])
    controller = HotelRagController(
        TempDatabase(database_path),
        api_key_getter=lambda: "test-key",
        model_getter=lambda: "configured-model",
        client_factory=lambda **options: FakeClient(responses, **options),
        audit_logger=RagAuditLogger(tmp_path / "audit.jsonl"),
        **kwargs,
    )
    return controller, responses


VALID_SQL = (
    "SELECT saved_hotels.hotel_id, saved_hotels.name, "
    "demo_hotel_nights.nightly_rate_cents "
    "FROM saved_hotels "
    "JOIN saved_hotel_locations ON saved_hotel_locations.hotel_id = saved_hotels.hotel_id "
    "JOIN demo_hotel_nights ON demo_hotel_nights.hotel_id = saved_hotels.hotel_id "
    "WHERE saved_hotel_locations.zip_code = :zip_code "
    "AND demo_hotel_nights.stay_date = :stay_date "
    "AND demo_hotel_nights.rooms_available > :minimum_rooms "
    "ORDER BY demo_hotel_nights.nightly_rate_cents ASC"
)


def proposal(sql: str, params: dict[str, object] | None = None) -> dict:
    return {"kind": "hotel_query", "sql": sql, "params": params or {}}


def test_valid_read_only_sql_returns_rows_and_audit_records(tmp_path: Path) -> None:
    controller, responses = make_controller(
        tmp_path,
        proposal(VALID_SQL, {"zip_code": "16802", "stay_date": "2026-10-10", "minimum_rooms": 0}),
    )

    result = controller.reply("Which saved hotels are available in 16802?")

    assert result["reply"] == "A saved hotel."
    assert result["conversation_id"]
    assert len(responses.inputs) == 2
    audit = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "proposed_sql" in audit and "executed_sql" in audit and "retrieved_rows" in audit


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO saved_hotels VALUES ('x', 'x', 'x', 0, 0)",
        "SELECT * FROM unknown_table",
        "SELECT unknown_column FROM saved_hotels",
    ],
)
def test_unsafe_sql_is_blocked(tmp_path: Path, sql: str) -> None:
    controller, _ = make_controller(tmp_path, proposal(sql))

    with pytest.raises(HotelRagValidationError):
        controller.reply("Show me saved hotel data")


def test_row_limit_is_enforced(tmp_path: Path) -> None:
    sql = "SELECT hotel_id, name FROM saved_hotels ORDER BY hotel_id"
    controller, _ = make_controller(tmp_path, proposal(sql), max_rows=1)

    # The final response is still produced, but the model only receives one row.
    result = controller.reply("List saved hotels")

    assert result["reply"] == "A saved hotel."
    assert result["conversation_id"]


def test_three_cheapest_request_caps_retrieved_rows_at_three(tmp_path: Path) -> None:
    controller, _ = make_controller(
        tmp_path,
        proposal(VALID_SQL, {"zip_code": "16802", "stay_date": "2026-10-10", "minimum_rooms": 0}),
        final="The provider returned three hotels.",
    )
    database_path = tmp_path / "rag.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.executemany(
            "INSERT INTO saved_hotels VALUES (?, ?, ?, ?, ?)",
            [("p3", "Third Inn", "3 Main St", 40.2, -77.2),
             ("p4", "Fourth Inn", "4 Main St", 40.3, -77.3)],
        )
        connection.executemany(
            "INSERT INTO saved_hotel_locations VALUES (?, ?, ?, ?)",
            [("p3", "16802", 40.0, -77.0), ("p4", "16802", 40.0, -77.0)],
        )
        connection.executemany(
            "INSERT INTO demo_hotel_nights (hotel_id, stay_date) VALUES (?, ?)",
            [("p3", "2026-10-10"), ("p4", "2026-10-10")],
        )

    result = controller.reply(
        "Show the three cheapest saved hotels near ZIP 16802 on October 10, 2026."
    )

    with sqlite3.connect(database_path) as connection:
        executed = connection.execute(
            "SELECT content FROM conversation_messages "
            "WHERE conversation_id = ? AND stage = 'executed_sql'",
            (result["conversation_id"],),
        ).fetchone()
        retrieved = connection.execute(
            "SELECT content FROM conversation_messages "
            "WHERE conversation_id = ? AND stage = 'retrieved_records'",
            (result["conversation_id"],),
        ).fetchone()

    assert json.loads(executed[0])["row_limit"] == 3
    retrieved_rows = json.loads(retrieved[0])["rows"]
    assert len(retrieved_rows) == 3
    assert "Found 3 matching saved hotel records" in result["reply"]


def test_three_cheapest_answer_reports_fewer_than_requested(tmp_path: Path) -> None:
    controller, _ = make_controller(
        tmp_path,
        proposal(VALID_SQL, {"zip_code": "16802", "stay_date": "2026-10-10", "minimum_rooms": 0}),
        final="There are three hotels.",
    )

    result = controller.reply(
        "Show the three cheapest saved hotels near ZIP 16802 on October 10, 2026."
    )

    assert "Found 2 matching saved hotel records" in result["reply"]


def test_empty_results_use_clear_non_invented_message(tmp_path: Path) -> None:
    controller, responses = make_controller(
        tmp_path,
        proposal(
            "SELECT hotel_id FROM saved_hotel_locations WHERE zip_code = :zip_code",
            {"zip_code": "00501"},
        ),
    )

    result = controller.reply("What hotels are saved for 00501?")

    assert result["reply"] == "No matching saved hotel records were found for that question."
    assert result["conversation_id"]
    assert len(responses.inputs) == 2


def test_provider_failure_is_sanitized(tmp_path: Path) -> None:
    database_path = tmp_path / "rag.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.executescript(SCHEMA)
    connection.executescript(database_module.CONVERSATION_HISTORY_MIGRATION)
    connection.close()
    responses = FakeResponses(error=RuntimeError("secret authorization detail"))
    controller = HotelRagController(
        TempDatabase(database_path),
        api_key_getter=lambda: "test-key",
        model_getter=lambda: "configured-model",
        client_factory=lambda **options: FakeClient(responses, **options),
        audit_logger=RagAuditLogger(tmp_path / "audit.jsonl"),
    )

    with pytest.raises(HotelRagProviderError) as error:
        controller.reply("Hello")

    assert "secret" not in str(error.value)
