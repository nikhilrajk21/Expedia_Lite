"""Read-only-contract tests for the additive saved-hotel schema migration."""

import sqlite3
from pathlib import Path

import pytest

from backend.controllers import database_controller as database_module


def _controller(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> database_module.DatabaseController:
    monkeypatch.setattr(database_module, "DATABASE_PATH", tmp_path / "expedia_lite.sqlite3")
    monkeypatch.setattr(
        database_module,
        "DATA_DIRECTORY",
        Path(r"C:\Users\nikhi\Downloads\Expedia_lite\data"),
    )
    return database_module.DatabaseController()


def _table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]


@pytest.mark.parametrize("precreate_existing_schema", [False, True])
def test_saved_hotel_migration_works_for_fresh_and_existing_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    precreate_existing_schema: bool,
) -> None:
    controller = _controller(tmp_path, monkeypatch)
    if precreate_existing_schema:
        with controller.open() as connection:
            connection.executescript(database_module.SCHEMA)

    assert controller.initialize_database() is True
    assert controller.initialize_database() is False

    with controller.open() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "app_metadata",
            "bookings",
            "conversation_messages",
            "demo_hotel_nights",
            "hotels",
            "saved_hotels",
            "saved_hotel_locations",
            "trips",
            "users",
        }.issubset(tables)
        assert _table_columns(connection, "saved_hotels") == [
            "hotel_id",
            "name",
            "address",
            "latitude",
            "longitude",
        ]
        assert _table_columns(connection, "demo_hotel_nights") == [
            "hotel_id",
            "stay_date",
            "nightly_rate_cents",
            "rooms_available",
        ]
        assert _table_columns(connection, "saved_hotel_locations") == [
            "hotel_id",
            "zip_code",
            "latitude",
            "longitude",
        ]
        assert _table_columns(connection, "conversation_messages") == [
            "message_id",
            "conversation_id",
            "timestamp",
            "role",
            "stage",
            "content",
        ]
        assert connection.execute("SELECT COUNT(*) FROM saved_hotels").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM demo_hotel_nights").fetchone()[0] == 0


def _assert_integrity_error(
    connection: sqlite3.Connection, statement: str, parameters: tuple[object, ...]
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(statement, parameters)
    connection.rollback()


def test_saved_hotels_and_demo_nights_enforce_requested_constraints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller = _controller(tmp_path, monkeypatch)
    controller.initialize_database()

    with controller.open() as connection:
        connection.execute(
            "INSERT INTO saved_hotels (hotel_id, name, address, latitude, longitude) "
            "VALUES (?, ?, ?, ?, ?)",
            ("provider-1", None, None, 40.0, -77.0),
        )
        connection.execute(
            "INSERT INTO demo_hotel_nights (hotel_id, stay_date) VALUES (?, ?)",
            ("provider-1", "2026-10-01"),
        )
        connection.execute(
            "INSERT INTO saved_hotel_locations (hotel_id, zip_code, latitude, longitude) "
            "VALUES (?, ?, ?, ?)",
            ("provider-1", "00501", 40.0, -77.0),
        )
        connection.commit()

        defaults = connection.execute(
            "SELECT nightly_rate_cents, rooms_available FROM demo_hotel_nights "
            "WHERE hotel_id = ? AND stay_date = ?",
            ("provider-1", "2026-10-01"),
        ).fetchone()
        assert tuple(defaults) == (10000, 20)

        _assert_integrity_error(
            connection,
            "INSERT INTO saved_hotels (hotel_id, latitude, longitude) VALUES (?, ?, ?)",
            ("provider-1", 41.0, -78.0),
        )
        _assert_integrity_error(
            connection,
            "INSERT INTO demo_hotel_nights (hotel_id, stay_date) VALUES (?, ?)",
            ("provider-1", "2026-10-01"),
        )
        _assert_integrity_error(
            connection,
            "INSERT INTO saved_hotel_locations (hotel_id, zip_code, latitude, longitude) "
            "VALUES (?, ?, ?, ?)",
            ("provider-1", "00501", 40.0, -77.0),
        )
        _assert_integrity_error(
            connection,
            "INSERT INTO saved_hotel_locations (hotel_id, zip_code, latitude, longitude) "
            "VALUES (?, ?, ?, ?)",
            ("unknown-provider", "00502", 40.0, -77.0),
        )
        _assert_integrity_error(
            connection,
            "INSERT INTO demo_hotel_nights (hotel_id, stay_date) VALUES (?, ?)",
            ("unknown-provider", "2026-10-02"),
        )
        _assert_integrity_error(
            connection,
            "INSERT INTO saved_hotels (hotel_id, latitude, longitude) VALUES (?, ?, ?)",
            ("bad-latitude", 91.0, 0.0),
        )
        _assert_integrity_error(
            connection,
            "INSERT INTO saved_hotels (hotel_id, latitude, longitude) VALUES (?, ?, ?)",
            ("bad-longitude", 0.0, -181.0),
        )
        _assert_integrity_error(
            connection,
            "INSERT INTO demo_hotel_nights (hotel_id, stay_date) VALUES (?, ?)",
            ("provider-1", "2026-02-30"),
        )
        _assert_integrity_error(
            connection,
            "INSERT INTO demo_hotel_nights (hotel_id, stay_date, nightly_rate_cents) "
            "VALUES (?, ?, ?)",
            ("provider-1", "2026-10-02", -1),
        )
        _assert_integrity_error(
            connection,
            "INSERT INTO demo_hotel_nights (hotel_id, stay_date, rooms_available) "
            "VALUES (?, ?, ?)",
            ("provider-1", "2026-10-03", -1),
        )
