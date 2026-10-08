"""Business workflows for saving provider hotels to the local SQLite database."""

import math
from collections.abc import Mapping

from .database_controller import DatabaseController, ReferenceNotFoundError


DEMO_STAY_DATES = tuple(f"2026-10-{day:02d}" for day in range(10, 15))


class SavedHotelValidationError(ValueError):
    """Raised when a saved-hotel request is not safe to persist."""


class SavedHotelNotFoundError(LookupError):
    """Raised when a requested saved hotel does not exist."""


class SavedHotelPersistenceError(RuntimeError):
    """Raised when local saved-hotel persistence fails safely."""


class SavedHotelController:
    """Validate provider hotel fields and delegate persistence to SQLite."""

    def __init__(self, database: DatabaseController) -> None:
        self._database = database

    def save(self, request: Mapping[str, object]) -> dict[str, object]:
        hotel_id = request.get("place_id")
        if not isinstance(hotel_id, str) or not hotel_id.strip():
            raise SavedHotelValidationError("A provider hotel ID is required.")
        zip_code = _validate_zip(request.get("zip_code"))
        center = request.get("center")
        if not isinstance(center, Mapping):
            raise SavedHotelValidationError("A searched ZIP center is required.")

        name = _optional_text(request.get("name"))
        address = _optional_text(request.get("address"))
        latitude = _coordinate(request.get("latitude"), -90, 90, "hotel latitude")
        longitude = _coordinate(request.get("longitude"), -180, 180, "hotel longitude")
        search_latitude = _coordinate(
            center.get("latitude"), -90, 90, "search latitude"
        )
        search_longitude = _coordinate(
            center.get("longitude"), -180, 180, "search longitude"
        )
        try:
            return self._database.save_saved_hotel(
                hotel_id=hotel_id,
                name=name,
                address=address,
                latitude=latitude,
                longitude=longitude,
                zip_code=zip_code,
                search_latitude=search_latitude,
                search_longitude=search_longitude,
                stay_dates=DEMO_STAY_DATES,
            )
        except Exception as error:
            # The route must not surface SQL details or credential-containing text.
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            raise SavedHotelPersistenceError("Saved hotel could not be stored.") from None

    def list_for_zip(self, zip_code: object) -> list[dict[str, object]]:
        normalized_zip = _validate_zip(zip_code)
        try:
            return self._database.list_saved_hotels_for_zip(normalized_zip)
        except Exception as error:
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            raise SavedHotelPersistenceError("Saved hotels could not be loaded.") from None

    def remove(self, hotel_id: str) -> None:
        if not isinstance(hotel_id, str) or not hotel_id:
            raise SavedHotelValidationError("A provider hotel ID is required.")
        try:
            self._database.delete_saved_hotel(hotel_id)
        except ReferenceNotFoundError:
            raise SavedHotelNotFoundError("Saved hotel was not found.") from None
        except Exception as error:
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            raise SavedHotelPersistenceError("Saved hotel could not be removed.") from None


def _validate_zip(value: object) -> str:
    if not isinstance(value, str):
        raise SavedHotelValidationError("ZIP code must be exactly five ASCII digits.")
    zip_code = value.strip()
    if len(zip_code) != 5 or not all("0" <= character <= "9" for character in zip_code):
        raise SavedHotelValidationError("ZIP code must be exactly five ASCII digits.")
    return zip_code


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SavedHotelValidationError("Hotel text fields must be strings.")
    value = value.strip()
    return value or None


def _coordinate(value: object, minimum: float, maximum: float, label: str) -> float:
    if isinstance(value, bool):
        raise SavedHotelValidationError(f"{label} is invalid.")
    try:
        coordinate = float(value)
    except (TypeError, ValueError):
        raise SavedHotelValidationError(f"{label} is invalid.") from None
    if not math.isfinite(coordinate) or not minimum <= coordinate <= maximum:
        raise SavedHotelValidationError(f"{label} is invalid.")
    return coordinate


__all__ = [
    "DEMO_STAY_DATES",
    "SavedHotelController",
    "SavedHotelNotFoundError",
    "SavedHotelPersistenceError",
    "SavedHotelValidationError",
]
