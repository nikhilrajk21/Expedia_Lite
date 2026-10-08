"""Conversation identity, context, and persistence tests for hotel RAG."""

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.controllers import database_controller as database_module
from backend.controllers.conversation_controller import ConversationController
from backend.controllers.hotel_rag_controller import (
    HotelRagController,
    HotelRagProviderError,
    RagAuditLogger,
)


SCHEMA = """
CREATE TABLE saved_hotels (
    hotel_id TEXT PRIMARY KEY, name TEXT, address TEXT,
    latitude REAL NOT NULL, longitude REAL NOT NULL
);
CREATE TABLE saved_hotel_locations (
    hotel_id TEXT NOT NULL, zip_code TEXT NOT NULL,
    latitude REAL NOT NULL, longitude REAL NOT NULL,
    PRIMARY KEY (hotel_id, zip_code)
);
CREATE TABLE demo_hotel_nights (
    hotel_id TEXT NOT NULL, stay_date TEXT NOT NULL,
    nightly_rate_cents INTEGER NOT NULL DEFAULT 10000,
    rooms_available INTEGER NOT NULL DEFAULT 20,
    PRIMARY KEY (hotel_id, stay_date)
);
"""


class TempDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path

    def open(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
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
        self.outputs = list(outputs or [])
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


def make_database(tmp_path: Path) -> TempDatabase:
    path = tmp_path / "conversation.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    connection.executescript(database_module.CONVERSATION_HISTORY_MIGRATION)
    connection.execute(
        "INSERT INTO saved_hotels VALUES (?, ?, ?, ?, ?)",
        ("p1", "Sleep Inn", "1 Main St", 40.0, -77.0),
    )
    connection.execute(
        "INSERT INTO saved_hotel_locations VALUES (?, ?, ?, ?)",
        ("p1", "16802", 40.0, -77.0),
    )
    connection.executemany(
        "INSERT INTO demo_hotel_nights VALUES (?, ?, ?, ?)",
        [("p1", "2026-10-11", 10000, 20), ("p1", "2026-10-12", 10000, 20)],
    )
    connection.commit()
    connection.close()
    return TempDatabase(path)


def sql_for(date_value: str, zip_code: str = "16802") -> tuple[str, dict[str, object]]:
    return (
        "SELECT saved_hotels.name, saved_hotel_locations.zip_code, "
        "demo_hotel_nights.stay_date, demo_hotel_nights.nightly_rate_cents, "
        "demo_hotel_nights.rooms_available "
        "FROM saved_hotels "
        "JOIN saved_hotel_locations ON saved_hotel_locations.hotel_id = saved_hotels.hotel_id "
        "JOIN demo_hotel_nights ON demo_hotel_nights.hotel_id = saved_hotels.hotel_id "
        "WHERE saved_hotel_locations.zip_code = :zip_code "
        "AND demo_hotel_nights.stay_date = :stay_date "
        "AND demo_hotel_nights.rooms_available > :minimum_rooms",
        {"zip_code": zip_code, "stay_date": date_value, "minimum_rooms": 0},
    )


def make_controller(database: TempDatabase, responses: FakeResponses, tmp_path: Path):
    return HotelRagController(
        database,
        conversation_controller=ConversationController(database),
        api_key_getter=lambda: "test-key",
        model_getter=lambda: "configured-model",
        client_factory=lambda **kwargs: FakeClient(responses, **kwargs),
        audit_logger=RagAuditLogger(tmp_path / "audit.jsonl"),
    )


def proposal(sql: str, params: dict[str, object]) -> str:
    return json.dumps({"kind": "hotel_query", "sql": sql, "params": params})


def test_conversation_id_and_history_survive_new_controller(tmp_path: Path) -> None:
    database = make_database(tmp_path)
    sql, params = sql_for("2026-10-11")
    responses = FakeResponses([proposal(sql, params), "Sleep Inn is available."])
    controller = make_controller(database, responses, tmp_path)
    conversation_id = "4e3f0e34-5d4c-4e3d-8c1e-6bc11ab87000"

    result = controller.reply("Which saved hotel is available in 16802?", conversation_id)
    history = ConversationController(database).history(conversation_id)

    assert result["conversation_id"] == conversation_id
    assert [event["stage"] for event in history] == [
        "user_question",
        "sql_proposal",
        "executed_sql",
        "retrieved_records",
        "assistant_answer",
    ]
    restarted_controller = make_controller(
        database,
        FakeResponses([proposal(sql, params), "Again."]),
        tmp_path,
    )
    assert restarted_controller._conversation.history(conversation_id) == history


def test_follow_up_prompt_reuses_prior_zip_and_updates_date(tmp_path: Path) -> None:
    database = make_database(tmp_path)
    sql_11, params_11 = sql_for("2026-10-11")
    sql_12, params_12 = sql_for("2026-10-12")
    responses = FakeResponses(
        [proposal(sql_11, params_11), "First answer.", proposal(sql_12, params_12), "Second answer."]
    )
    controller = make_controller(database, responses, tmp_path)
    conversation_id = "79dd1a77-716b-4a35-a8a6-f0826a2e5c00"

    controller.reply("Which hotel is available in ZIP 16802 on October 11?", conversation_id)
    result = controller.reply("What about October 12?", conversation_id)

    assert result["reply"] == "Second answer."
    follow_up_prompt = responses.inputs[2]
    assert "16802" in follow_up_prompt
    assert "2026-10-11" in follow_up_prompt
    follow_up_history = ConversationController(database).history(conversation_id)
    proposals = [
        event["content"]
        for event in follow_up_history
        if event["stage"] == "sql_proposal"
    ]
    assert "2026-10-12" in proposals[-1]


def test_successful_rows_replace_contradictory_model_answer(tmp_path: Path) -> None:
    database = make_database(tmp_path)
    sql, params = sql_for("2026-10-11")
    responses = FakeResponses(
        [proposal(sql, params), "No matching saved records were found, but Sleep Inn is listed."]
    )

    result = make_controller(database, responses, tmp_path).reply("Show the hotel")

    assert "No matching saved records" not in result["reply"]
    assert "Sleep Inn" in result["reply"]
    assert "$100.00" in result["reply"]


def test_no_match_returns_clear_message(tmp_path: Path) -> None:
    database = make_database(tmp_path)
    sql, params = sql_for("2026-10-11", zip_code="00501")
    responses = FakeResponses([proposal(sql, params), "irrelevant provider wording"])

    result = make_controller(database, responses, tmp_path).reply("Search 00501")

    assert result["reply"] == "No matching saved hotel records were found for that question."


def test_provider_failure_records_error_without_assistant_answer(tmp_path: Path) -> None:
    database = make_database(tmp_path)
    responses = FakeResponses(error=RuntimeError("credential-bearing provider failure"))
    controller = make_controller(database, responses, tmp_path)
    conversation_id = "28bc1a8b-3c77-49a3-9bb4-1b2a29be4a00"

    with pytest.raises(HotelRagProviderError):
        controller.reply("Search saved hotels", conversation_id)

    history = ConversationController(database).history(conversation_id)
    assert [event["stage"] for event in history] == ["user_question", "error"]
    assert "credential" not in " ".join(event["content"] for event in history)
