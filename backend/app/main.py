"""FastAPI endpoints for Expedia Lite hotel search."""

from contextlib import asynccontextmanager
from datetime import date
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

try:  # Supports backend-directory Uvicorn and project-root test imports.
    from controllers import (
        BookingController,
        CreateBookingCommand,
        DatabaseController,
        HotelController,
        ReferenceNotFoundError,
        TestBookingDeletionError,
    )
except ModuleNotFoundError:  # pragma: no cover - depends on launch directory
    from backend.controllers import (
        BookingController,
        CreateBookingCommand,
        DatabaseController,
        HotelController,
        ReferenceNotFoundError,
        TestBookingDeletionError,
    )

database_controller = DatabaseController()
hotel_controller = HotelController(database_controller)
booking_controller = BookingController(database_controller)

class BookingCreateRequest(BaseModel):
    """Frontend request for a booking; the server owns booking ID and status."""

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1)
    trip_id: str = Field(min_length=1)
    booked_on: date
    is_test: bool = False


class BookingStatusUpdateRequest(BaseModel):
    """Cancellation is the only permitted status transition in Part 2."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["cancelled"]

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize the MVC database controller without changing API contracts."""
    database_controller.initialize_database()
    yield


app = FastAPI(title="Expedia Lite API", lifespan=lifespan)


@app.get("/api/hotels/search")
def search_hotels(name: str = Query(default="", description="Hotel-name search text")) -> dict:
    """Return SQLite-backed hotels matching a name and their connected stays."""
    return {"results": hotel_controller.search(name)}


@app.post("/api/bookings", status_code=status.HTTP_201_CREATED)
def create_new_booking(request: BookingCreateRequest) -> dict:
    """Create a confirmed SQLite booking using an automatically assigned ID."""
    try:
        booking = booking_controller.create(
            CreateBookingCommand(
                user_id=request.user_id,
                trip_id=request.trip_id,
                booked_on=request.booked_on.isoformat(),
                is_test=request.is_test,
            )
        )
    except ReferenceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return {"booking": booking}


@app.get("/api/bookings")
def get_booking_history() -> dict:
    """Return SQLite booking history, including retained cancelled bookings."""
    return {"bookings": booking_controller.history()}


@app.patch("/api/bookings/{booking_id}")
def cancel_existing_booking(
    booking_id: str, request: BookingStatusUpdateRequest
) -> dict:
    """Cancel a booking without deleting the record."""
    try:
        booking = booking_controller.cancel(booking_id)
    except ReferenceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return {"booking": booking}


@app.delete("/api/bookings/{booking_id}")
def delete_existing_test_booking(booking_id: str) -> dict:
    """Delete a test booking while preserving all seeded/normal records."""
    try:
        booking_controller.delete_test(booking_id)
    except ReferenceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except TestBookingDeletionError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return {"deleted_booking_id": booking_id}
