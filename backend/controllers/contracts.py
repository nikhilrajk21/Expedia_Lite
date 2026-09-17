"""Controller contracts shared by FastAPI routes and business controllers."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CreateBookingCommand:
    """Input from the API controller to the booking business controller."""

    user_id: str
    trip_id: str
    booked_on: str
    is_test: bool
