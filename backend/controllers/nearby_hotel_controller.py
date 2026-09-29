"""Geoapify Places controller for hotels near a resolved ZIP location."""

import math
from collections.abc import Callable, Mapping
from typing import Any

import httpx

try:  # Supports backend-directory Uvicorn and project-root test imports.
    from app.config import get_geoapify_api_key
except ModuleNotFoundError:  # pragma: no cover - depends on launch directory
    from backend.app.config import get_geoapify_api_key


GEOAPIFY_PLACES_ENDPOINT = "https://api.geoapify.com/v2/places"
HOTEL_CATEGORY = "accommodation.hotel"
SEARCH_RADIUS_METERS = 5000
REQUEST_TIMEOUT_SECONDS = 10.0


class NearbyHotelProviderError(Exception):
    """Raised when the Places provider request or response cannot be used."""


class NearbyHotelInvalidDataError(NearbyHotelProviderError):
    """Raised when a provider hotel is missing required identity or coordinates."""


class NearbyHotelNoResultsError(Exception):
    """Raised when the Places provider returns no valid hotel features."""


class NearbyHotelController:
    """Find provider-backed hotels around the coordinates resolved for a ZIP."""

    def __init__(
        self,
        zip_lookup: Callable[[str], Mapping[str, object]],
        api_key_getter: Callable[[], str | None] = get_geoapify_api_key,
        http_get: Callable[..., httpx.Response] = httpx.get,
    ) -> None:
        self._zip_lookup = zip_lookup
        self._api_key_getter = api_key_getter
        self._http_get = http_get

    def find_nearby_hotels(self, zip_code: str) -> list[dict[str, object]]:
        """Return sanitized provider fields for hotels within 5 km of ``zip_code``."""
        location = self._zip_lookup(zip_code)
        return self.find_nearby_hotels_at_location(location)

    def find_nearby_hotels_at_location(
        self, location: Mapping[str, object]
    ) -> list[dict[str, object]]:
        """Return sanitized hotels around an already-resolved location."""
        latitude = _valid_coordinate(location.get("latitude"), -90, 90)
        longitude = _valid_coordinate(location.get("longitude"), -180, 180)
        if latitude is None or longitude is None:
            raise NearbyHotelProviderError("ZIP location returned invalid coordinates.")

        api_key = self._api_key_getter()
        if not api_key:
            raise NearbyHotelProviderError("Nearby hotel provider is not configured.")

        try:
            response = self._http_get(
                GEOAPIFY_PLACES_ENDPOINT,
                params={
                    "categories": HOTEL_CATEGORY,
                    "filter": f"circle:{longitude},{latitude},{SEARCH_RADIUS_METERS}",
                    "limit": 20,
                    "apiKey": api_key,
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError, TypeError):
            # Provider exception text may contain the credential-bearing request URL.
            raise NearbyHotelProviderError(
                "Nearby hotel provider is unavailable."
            ) from None

        hotels = _sanitized_hotels(payload)
        if hotels is None:
            raise NearbyHotelProviderError("Nearby hotel provider returned an invalid response.")
        if not hotels:
            raise NearbyHotelNoResultsError("No hotels were found near the requested ZIP.")
        return hotels


def _sanitized_hotels(payload: object) -> list[dict[str, object]] | None:
    """Return only real provider identity, address, and coordinate fields."""
    if not isinstance(payload, Mapping):
        return None

    features = payload.get("features")
    if not isinstance(features, list):
        return None
    if not features:
        return []

    hotels: list[dict[str, object]] = []
    for feature in features:
        if not isinstance(feature, Mapping):
            raise NearbyHotelInvalidDataError(
                "Nearby hotel provider returned incomplete hotel data."
            )
        properties = feature.get("properties")
        if not isinstance(properties, Mapping):
            raise NearbyHotelInvalidDataError(
                "Nearby hotel provider returned incomplete hotel data."
            )

        place_id = _text_value(properties.get("place_id"))
        name = _text_value(properties.get("name"))
        latitude = _valid_coordinate(properties.get("lat"), -90, 90)
        longitude = _valid_coordinate(properties.get("lon"), -180, 180)
        if (
            place_id is None
            or name is None
            or latitude is None
            or longitude is None
        ):
            raise NearbyHotelInvalidDataError(
                "Nearby hotel provider returned incomplete hotel data."
            )

        hotel: dict[str, object] = {
            "place_id": place_id,
            "name": name,
            "latitude": latitude,
            "longitude": longitude,
        }
        address = _first_text(properties, ("formatted", "address_line1", "address"))
        locality = _first_text(properties, ("city", "locality"))
        if address is not None:
            hotel["address"] = address
        if locality is not None:
            hotel["locality"] = locality
        hotels.append(hotel)

    return hotels


def _valid_coordinate(value: object, minimum: float, maximum: float) -> float | None:
    """Return a finite coordinate within its geographical range."""
    if isinstance(value, bool):
        return None
    try:
        coordinate = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(coordinate) or not minimum <= coordinate <= maximum:
        return None
    return coordinate


def _text_value(value: object) -> str | None:
    """Return a non-blank provider string without manufacturing a value."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _first_text(properties: Mapping[str, Any], fields: tuple[str, ...]) -> str | None:
    """Select the first available provider field from an allowed set."""
    for field in fields:
        value = _text_value(properties.get(field))
        if value is not None:
            return value
    return None
