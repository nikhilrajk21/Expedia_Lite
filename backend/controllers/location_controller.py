"""Backend-only Geoapify postcode lookup controller."""

import math
from collections.abc import Callable, Mapping
from typing import Any

import httpx

try:  # Supports backend-directory Uvicorn and project-root test imports.
    from app.config import get_geoapify_api_key
except ModuleNotFoundError:  # pragma: no cover - depends on launch directory
    from backend.app.config import get_geoapify_api_key


DEMONSTRATION_POSTCODE = "16802"
GEOAPIFY_FORWARD_GEOCODING_ENDPOINT = "https://api.geoapify.com/v1/geocode/search"
REQUEST_TIMEOUT_SECONDS = 10.0


class ZipLookupUnresolvedError(Exception):
    """Raised when the provider responds but cannot identify the requested ZIP."""


class ZipLookupProviderError(Exception):
    """Raised when the provider cannot be contacted or its response is unusable."""


class ZipLookupConfigurationError(Exception):
    """Raised when the backend-only Geoapify key is not configured."""


class InvalidZipCodeError(Exception):
    """Raised when a requested ZIP is not exactly five ASCII digits."""


class LocationController:
    """Look up validated U.S. ZIP codes without exposing backend secrets."""

    def __init__(
        self,
        api_key_getter: Callable[[], str | None] = get_geoapify_api_key,
        http_get: Callable[..., httpx.Response] = httpx.get,
    ) -> None:
        self._api_key_getter = api_key_getter
        self._http_get = http_get

    def lookup_demo_postcode(self, zip_code: str) -> dict[str, object]:
        """Return a validated location for a user-supplied five-digit ZIP string."""
        requested_postcode = _validate_zip_code(zip_code)
        api_key = self._api_key_getter()
        if not api_key:
            raise ZipLookupConfigurationError("ZIP lookup is not configured.")

        try:
            response = self._http_get(
                GEOAPIFY_FORWARD_GEOCODING_ENDPOINT,
                params={
                    "text": requested_postcode,
                    "type": "postcode",
                    "filter": "countrycode:us",
                    "format": "json",
                    "limit": 1,
                    "apiKey": api_key,
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError, TypeError):
            # Do not surface exception text: HTTP exception strings may include the key.
            raise ZipLookupProviderError("ZIP lookup provider is unavailable.") from None

        location = _validated_location(payload, requested_postcode)
        if location is None:
            raise ZipLookupUnresolvedError(
                f"ZIP code {requested_postcode} could not be resolved."
            )
        return location


def _validate_zip_code(zip_code: str) -> str:
    """Trim and validate a ZIP while preserving it as a string, including leading zeros."""
    if not isinstance(zip_code, str):
        raise InvalidZipCodeError("ZIP code must be exactly five ASCII digits.")

    requested_postcode = zip_code.strip()
    if len(requested_postcode) != 5 or not all(
        "0" <= character <= "9" for character in requested_postcode
    ):
        raise InvalidZipCodeError("ZIP code must be exactly five ASCII digits.")
    return requested_postcode


def _validated_location(
    payload: object, requested_postcode: str
) -> dict[str, object] | None:
    """Select only an exact US postcode match with finite, in-range coordinates."""
    if not isinstance(payload, Mapping):
        raise ZipLookupProviderError("ZIP lookup provider returned an invalid response.")

    results = payload.get("results")
    if not isinstance(results, list):
        raise ZipLookupProviderError("ZIP lookup provider returned an invalid response.")

    for result in results:
        if not isinstance(result, Mapping):
            continue

        postcode = result.get("postcode")
        country_code = result.get("country_code")
        latitude = _valid_coordinate(result.get("lat"), -90, 90)
        longitude = _valid_coordinate(result.get("lon"), -180, 180)

        if (
            postcode != requested_postcode
            or not isinstance(country_code, str)
            or country_code.casefold() != "us"
            or latitude is None
            or longitude is None
        ):
            continue

        location: dict[str, object] = {
            "postcode": requested_postcode,
            "country_code": "us",
            "latitude": latitude,
            "longitude": longitude,
        }
        locality = _locality(result)
        if locality is not None:
            location["locality"] = locality
        return location

    return None


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


def _locality(result: Mapping[str, Any]) -> str | None:
    """Use Geoapify's city/locality value only when it is a non-blank string."""
    for field in ("city", "locality"):
        value = result.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
