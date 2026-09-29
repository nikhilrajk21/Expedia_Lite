"""Mocked tests for Geoapify Places hotel retrieval."""

from unittest.mock import Mock

import httpx
import pytest

from backend.controllers.nearby_hotel_controller import (
    GEOAPIFY_PLACES_ENDPOINT,
    HOTEL_CATEGORY,
    REQUEST_TIMEOUT_SECONDS,
    SEARCH_RADIUS_METERS,
    NearbyHotelController,
    NearbyHotelInvalidDataError,
    NearbyHotelNoResultsError,
    NearbyHotelProviderError,
)
from backend.controllers.location_controller import ZipLookupUnresolvedError


ZIP_LOCATION = {
    "postcode": "16802",
    "country_code": "us",
    "latitude": 40.803167822,
    "longitude": -77.861384958,
}


def _controller(http_get: Mock) -> NearbyHotelController:
    return NearbyHotelController(
        zip_lookup=lambda _: ZIP_LOCATION,
        api_key_getter=lambda: "test-key",
        http_get=http_get,
    )


def test_find_nearby_hotels_returns_sanitized_provider_fields() -> None:
    http_get = Mock()
    response = Mock()
    response.json.return_value = {
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "place_id": "provider-place-1",
                    "name": "Provider Hotel",
                    "formatted": "1 Main Street, State College, PA",
                    "city": "State College",
                    "lat": 40.804,
                    "lon": -77.862,
                    "price": 999,
                    "rating": 5,
                },
            }
        ]
    }
    http_get.return_value = response

    assert _controller(http_get).find_nearby_hotels("16802") == [
        {
            "place_id": "provider-place-1",
            "name": "Provider Hotel",
            "latitude": 40.804,
            "longitude": -77.862,
            "address": "1 Main Street, State College, PA",
            "locality": "State College",
        }
    ]
    http_get.assert_called_once_with(
        GEOAPIFY_PLACES_ENDPOINT,
        params={
            "categories": HOTEL_CATEGORY,
            "filter": f"circle:-77.861384958,40.803167822,{SEARCH_RADIUS_METERS}",
            "limit": 20,
            "apiKey": "test-key",
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )


def test_find_nearby_hotels_distinguishes_empty_results() -> None:
    http_get = Mock()
    response = Mock()
    response.json.return_value = {"features": []}
    http_get.return_value = response

    with pytest.raises(NearbyHotelNoResultsError):
        _controller(http_get).find_nearby_hotels("16802")


def test_find_nearby_hotels_distinguishes_incomplete_provider_fields() -> None:
    http_get = Mock()
    response = Mock()
    response.json.return_value = {
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "place_id": "provider-place-1",
                    "name": "Provider Hotel",
                    "lat": 40.804,
                },
            }
        ]
    }
    http_get.return_value = response

    with pytest.raises(NearbyHotelInvalidDataError):
        _controller(http_get).find_nearby_hotels("16802")


def test_find_nearby_hotels_hides_provider_failure_details() -> None:
    http_get = Mock(side_effect=httpx.TimeoutException("request included test-key"))

    with pytest.raises(NearbyHotelProviderError, match="provider is unavailable") as error:
        _controller(http_get).find_nearby_hotels("16802")

    assert "test-key" not in str(error.value)


def test_find_nearby_hotels_propagates_unresolved_zip() -> None:
    http_get = Mock()
    unresolved = Mock(side_effect=ZipLookupUnresolvedError("not resolved"))
    controller = NearbyHotelController(
        zip_lookup=unresolved,
        api_key_getter=lambda: "test-key",
        http_get=http_get,
    )

    with pytest.raises(ZipLookupUnresolvedError):
        controller.find_nearby_hotels("16802")

    http_get.assert_not_called()
