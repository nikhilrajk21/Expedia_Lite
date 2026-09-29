"""Compatibility facade for the pre-MVC database module.

New application code must use backend/controllers. These re-exports keep any
older import path working while routing every operation through DatabaseController.
"""

try:  # Supports backend-directory Uvicorn and project-root test imports.
    from controllers import DATABASE_PATH, DatabaseController
except ModuleNotFoundError:  # pragma: no cover - depends on launch directory
    from backend.controllers import DATABASE_PATH, DatabaseController


_database = DatabaseController()


def get_connection():
    return _database.open()


def read_csv_rows(filename: str):
    return _database._read_csv_rows(filename)


def initialize_database() -> bool:
    return _database.initialize_database()


def search_hotels_by_name(name: str) -> list[dict[str, object]]:
    return _database.search_hotels(name)


def create_booking(*, user_id: str, trip_id: str, booked_on: str, is_test: bool):
    return _database.create_booking(
        user_id=user_id, trip_id=trip_id, booked_on=booked_on, is_test=is_test
    ).to_dict()


def list_booking_history() -> list[dict[str, object]]:
    return _database.list_booking_history()


def cancel_booking(booking_id: str):
    return _database.cancel_booking(booking_id).to_dict()


def delete_test_booking(booking_id: str) -> None:
    _database.delete_test_booking(booking_id)
