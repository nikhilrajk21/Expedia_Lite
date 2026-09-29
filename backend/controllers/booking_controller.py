"""Booking business controller."""

from .contracts import CreateBookingCommand
from .database_controller import DatabaseController


class BookingController:
    """Contracts for booking workflows used by the FastAPI controller."""

    def __init__(self, database: DatabaseController) -> None:
        self._database = database

    def create(self, command: CreateBookingCommand) -> dict[str, object]:
        """Create a confirmed booking after database reference checks."""
        return self._database.create_booking(
            user_id=command.user_id,
            trip_id=command.trip_id,
            booked_on=command.booked_on,
            is_test=command.is_test,
        ).to_dict()

    def history(self) -> list[dict[str, object]]:
        return self._database.list_booking_history()

    def cancel(self, booking_id: str) -> dict[str, object]:
        return self._database.cancel_booking(booking_id).to_dict()

    def delete_test(self, booking_id: str) -> None:
        self._database.delete_test_booking(booking_id)
