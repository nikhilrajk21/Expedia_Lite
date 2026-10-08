"""Temporary-database mutation tests for local provider hotel persistence."""

import sqlite3
from pathlib import Path

import pytest

from backend.controllers import database_controller as database_module
from backend.controllers.saved_hotel_controller import (
    DEMO_STAY_DATES,
    SavedHotelController,
    SavedHotelNotFoundError,
    SavedHotelValidationError,
)


def _controller(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SavedHotelController:
    monkeypatch.setattr(database_module, "DATABASE_PATH", tmp_path / "expedia_lite.sqlite3")
    monkeypatch.setattr(
        database_module,
        "DATA_DIRECTORY",
        Path(r"C:\Users\nikhi\Downloads\Expedia_lite\data"),
    )
    database = database_module.DatabaseController()
    database.initialize_database()
    return SavedHotelController(database)


def _request(place_id: str = "provider-1", zip_code: str = "00501") -> dict[str, object]:
    return {
        "place_id": place_id,
        "name": "Demo Provider Hotel",
        "address": "1 Main Street",
        "latitude": 40.803,
        "longitude": -77.861,
        "zip_code": zip_code,
        "center": {"latitude": 40.8, "longitude": -77.86},
    }


def test_save_is_idempotent_and_creates_demo_nights_and_zip_association(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller = _controller(tmp_path, monkeypatch)

    first = controller.save(_request())
    second_request = _request()
    second_request["name"] = "A changed name that must not overwrite"
    second = controller.save(second_request)
    another_zip = controller.save(_request(zip_code="16802"))

    assert first["hotel"] == second["hotel"]
    assert another_zip["hotel"] == first["hotel"]
    assert len(first["nights"]) == len(DEMO_STAY_DATES) == 5
    assert all(
        night["nightly_rate_cents"] == 10000 and night["rooms_available"] == 20
        for night in first["nights"]
    )
    assert controller.list_for_zip("00501") == [
        {
            "place_id": "provider-1",
            "name": "Demo Provider Hotel",
            "address": "1 Main Street",
            "latitude": 40.803,
            "longitude": -77.861,
            "zip_code": "00501",
            "center": {"latitude": 40.8, "longitude": -77.86},
            "nights": [
                {
                    "stay_date": date,
                    "nightly_rate_cents": 10000,
                    "rooms_available": 20,
                }
                for date in DEMO_STAY_DATES
            ],
        }
    ]
    assert len(controller.list_for_zip("16802")) == 1

    with controller._database.open() as connection:
        assert connection.execute("SELECT COUNT(*) FROM saved_hotels").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM saved_hotel_locations").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM demo_hotel_nights").fetchone()[0] == 5


def test_remove_deletes_dependents_and_preserves_unrelated_saved_hotel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller = _controller(tmp_path, monkeypatch)
    controller.save(_request("provider-1"))
    controller.save(_request("provider-2", "16802"))

    controller.remove("provider-1")

    with controller._database.open() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM saved_hotels WHERE hotel_id = ?", ("provider-1",)
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM saved_hotel_locations WHERE hotel_id = ?", ("provider-1",)
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM demo_hotel_nights WHERE hotel_id = ?", ("provider-1",)
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM saved_hotels WHERE hotel_id = ?", ("provider-2",)
        ).fetchone()[0] == 1

    with pytest.raises(SavedHotelNotFoundError):
        controller.remove("provider-1")


@pytest.mark.parametrize("value", ["", "1234", "123456", "12A45", "12 45", "  "])
def test_save_rejects_invalid_zip_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    controller = _controller(tmp_path, monkeypatch)
    request = _request(zip_code=value)

    with pytest.raises(SavedHotelValidationError):
        controller.save(request)

    with controller._database.open() as connection:
        assert connection.execute("SELECT COUNT(*) FROM saved_hotels").fetchone()[0] == 0


def test_database_foreign_keys_remain_enabled_after_mutations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller = _controller(tmp_path, monkeypatch)
    with controller._database.open() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO saved_hotel_locations (hotel_id, zip_code, latitude, longitude) "
                "VALUES (?, ?, ?, ?)",
                ("missing", "00501", 40.0, -77.0),
            )
