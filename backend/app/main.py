"""FastAPI endpoints for Expedia Lite hotel search."""

from contextlib import asynccontextmanager
from datetime import date
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from .config import is_geoapify_api_key_configured

try:  # Supports backend-directory Uvicorn and project-root test imports.
    from controllers import (
        BookingController,
        ChatConfigurationError,
        ChatController,
        ChatProviderError,
        ChatValidationError,
        CreateBookingCommand,
        ConversationController,
        ConversationPersistenceError,
        ConversationValidationError,
        DatabaseController,
        HotelController,
        HotelRagConfigurationError,
        HotelRagController,
        HotelRagExecutionError,
        HotelRagProviderError,
        HotelRagValidationError,
        InvalidZipCodeError,
        LocationController,
        NearbyHotelController,
        NearbyHotelInvalidDataError,
        NearbyHotelNoResultsError,
        NearbyHotelProviderError,
        ReferenceNotFoundError,
        SavedHotelController,
        SavedHotelNotFoundError,
        SavedHotelPersistenceError,
        SavedHotelValidationError,
        TestBookingDeletionError,
        ZipLookupConfigurationError,
        ZipLookupProviderError,
        ZipLookupUnresolvedError,
    )
except ModuleNotFoundError:  # pragma: no cover - depends on launch directory
    from backend.controllers import (
        BookingController,
        ChatConfigurationError,
        ChatController,
        ChatProviderError,
        ChatValidationError,
        CreateBookingCommand,
        ConversationController,
        ConversationPersistenceError,
        ConversationValidationError,
        DatabaseController,
        HotelController,
        HotelRagConfigurationError,
        HotelRagController,
        HotelRagExecutionError,
        HotelRagProviderError,
        HotelRagValidationError,
        InvalidZipCodeError,
        LocationController,
        NearbyHotelController,
        NearbyHotelInvalidDataError,
        NearbyHotelNoResultsError,
        NearbyHotelProviderError,
        ReferenceNotFoundError,
        SavedHotelController,
        SavedHotelNotFoundError,
        SavedHotelPersistenceError,
        SavedHotelValidationError,
        TestBookingDeletionError,
        ZipLookupConfigurationError,
        ZipLookupProviderError,
        ZipLookupUnresolvedError,
    )

database_controller = DatabaseController()
hotel_controller = HotelController(database_controller)
booking_controller = BookingController(database_controller)
basic_chat_controller = ChatController()
conversation_controller = ConversationController(database_controller)
chat_controller = HotelRagController(
    database_controller,
    conversation_controller=conversation_controller,
    fallback_chat_controller=basic_chat_controller,
)
hotel_rag_controller = chat_controller
location_controller = LocationController()
nearby_hotel_controller = NearbyHotelController(location_controller.lookup_demo_postcode)
saved_hotel_controller = SavedHotelController(database_controller)

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


class ChatRequest(BaseModel):
    """One labeled message sent to the configured hotel assistant."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=100)


class SavedHotelSearchCenterRequest(BaseModel):
    """Resolved ZIP center supplied with a provider hotel save."""

    model_config = ConfigDict(extra="forbid")

    latitude: float
    longitude: float


class SavedHotelRequest(BaseModel):
    """Provider hotel fields plus the ZIP search context to associate."""

    model_config = ConfigDict(extra="forbid")

    place_id: str = Field(min_length=1)
    name: str | None = None
    address: str | None = None
    latitude: float
    longitude: float
    zip_code: str
    center: SavedHotelSearchCenterRequest

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize the MVC database controller without changing API contracts."""
    database_controller.initialize_database()
    yield


app = FastAPI(title="Expedia Lite API", lifespan=lifespan)


@app.get("/api/health")
def get_health() -> dict:
    """Return backend health and whether the Geoapify key is usable."""
    key_status = (
        "key is configured"
        if is_geoapify_api_key_configured()
        else "key is not configured"
    )
    return {"status": "ok", "geoapify_api_key": key_status}


@app.post("/api/chat")
def send_chat_message(request: ChatRequest) -> dict[str, str]:
    """Return one safe hotel-aware response and its persistent conversation ID."""
    try:
        if request.conversation_id is None:
            return chat_controller.reply(request.message)
        return chat_controller.reply(
            request.message,
            conversation_id=request.conversation_id,
        )
    except ChatValidationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message cannot be empty or too long.",
        ) from None
    except ChatConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat is not configured.",
        ) from None
    except ChatProviderError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Chat provider is unavailable.",
        ) from None
    except HotelRagConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat is not configured.",
        ) from None
    except HotelRagValidationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The hotel question could not be safely processed.",
        ) from None
    except HotelRagExecutionError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="The hotel search took too long.",
        ) from None
    except HotelRagProviderError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Chat provider is unavailable.",
        ) from None
    except ConversationValidationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Conversation ID is invalid.",
        ) from None
    except ConversationPersistenceError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Conversation history is unavailable.",
        ) from None


@app.get("/api/chat/history")
def get_chat_history(
    conversation_id: str = Query(..., description="Conversation UUID")
) -> dict[str, object]:
    """Load labeled chat history for a conversation after refresh or restart."""
    try:
        normalized_id = conversation_controller.normalize_id(conversation_id)
        messages = conversation_controller.history(normalized_id)
        return {"conversation_id": normalized_id, "messages": messages}
    except ConversationValidationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Conversation ID is invalid.",
        ) from None
    except ConversationPersistenceError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Conversation history is unavailable.",
        ) from None


@app.get("/api/demo/zip-location")
def get_demo_zip_location(
    zip_code: str = Query(..., description="Five-digit U.S. ZIP code")
) -> dict[str, object]:
    """Return the controller's validated location for a requested ZIP code."""
    try:
        return location_controller.lookup_demo_postcode(zip_code)
    except InvalidZipCodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ZIP code must be exactly five ASCII digits.",
        ) from None
    except ZipLookupConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ZIP lookup is not configured.",
        ) from None
    except ZipLookupUnresolvedError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requested ZIP code could not be resolved.",
        ) from None
    except ZipLookupProviderError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="ZIP lookup provider is unavailable.",
        ) from None


@app.get("/api/demo/nearby-hotels")
def get_nearby_hotels(
    zip_code: str = Query(..., description="Five-digit U.S. ZIP code")
) -> dict[str, list[dict[str, object]]]:
    """Return sanitized Geoapify hotel fields near a requested ZIP."""
    try:
        return {"results": nearby_hotel_controller.find_nearby_hotels(zip_code)}
    except InvalidZipCodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ZIP code must be exactly five ASCII digits.",
        ) from None
    except ZipLookupConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ZIP lookup is not configured.",
        ) from None
    except ZipLookupUnresolvedError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requested ZIP code could not be resolved.",
        ) from None
    except NearbyHotelNoResultsError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hotels were found near the requested ZIP.",
        ) from None
    except (ZipLookupProviderError, NearbyHotelProviderError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Nearby hotel provider is unavailable.",
        ) from None


@app.get("/api/hotels/nearby")
def get_hotels_nearby(
    zip_code: str = Query(..., description="Five-digit U.S. ZIP code")
) -> dict[str, object]:
    """Resolve a ZIP and return sanitized hotels within 5 km of its center."""
    try:
        location = location_controller.lookup_demo_postcode(zip_code)
        results = nearby_hotel_controller.find_nearby_hotels_at_location(location)
        return {
            "zip_code": location["postcode"],
            "center": {
                "latitude": location["latitude"],
                "longitude": location["longitude"],
            },
            "results": results,
        }
    except InvalidZipCodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ZIP code must be exactly five ASCII digits.",
        ) from None
    except ZipLookupConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ZIP lookup is not configured.",
        ) from None
    except ZipLookupUnresolvedError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requested ZIP code could not be resolved.",
        ) from None
    except NearbyHotelNoResultsError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hotels were found near the requested ZIP.",
        ) from None
    except ZipLookupProviderError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="ZIP lookup provider is unavailable.",
        ) from None
    except NearbyHotelInvalidDataError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Nearby hotel provider returned incomplete hotel data.",
        ) from None
    except NearbyHotelProviderError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Nearby hotel provider is unavailable.",
        ) from None


@app.get("/api/hotels/search")
def search_hotels(name: str = Query(default="", description="Hotel-name search text")) -> dict:
    """Return SQLite-backed hotels matching a name and their connected stays."""
    return {"results": hotel_controller.search(name)}


@app.post("/api/saved-hotels", status_code=status.HTTP_201_CREATED)
def save_provider_hotel(request: SavedHotelRequest) -> dict[str, object]:
    """Save one provider hotel and associate it with the searched ZIP."""
    try:
        return saved_hotel_controller.save(request.model_dump())
    except SavedHotelValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from None
    except SavedHotelPersistenceError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Saved hotel could not be stored.",
        ) from None


@app.get("/api/saved-hotels")
def get_saved_hotels(
    zip_code: str = Query(..., description="Five-digit searched ZIP code")
) -> dict[str, list[dict[str, object]]]:
    """Return locally saved provider hotels associated with a searched ZIP."""
    try:
        return {"results": saved_hotel_controller.list_for_zip(zip_code)}
    except SavedHotelValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from None
    except SavedHotelPersistenceError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Saved hotels could not be loaded.",
        ) from None


@app.delete("/api/saved-hotels/{hotel_id}")
def remove_saved_hotel(hotel_id: str) -> dict[str, str]:
    """Remove one saved provider hotel and its dependent local records."""
    try:
        saved_hotel_controller.remove(hotel_id)
    except SavedHotelValidationError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from None
    except SavedHotelNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved hotel was not found.",
        ) from None
    except SavedHotelPersistenceError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Saved hotel could not be removed.",
        ) from None
    return {"deleted_place_id": hotel_id}


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
