"""Mocked contract checks for the fixed Geoapify ZIP demonstration."""

from unittest.mock import Mock

import httpx
import pytest

from backend.controllers.location_controller import (
    DEMONSTRATION_POSTCODE,
    GEOAPIFY_FORWARD_GEOCODING_ENDPOINT,
    InvalidZipCodeError,
    REQUEST_TIMEOUT_SECONDS,
    LocationController,
    ZipLookupConfigurationError,
    ZipLookupProviderError,
    ZipLookupUnresolvedError,
)


def _controller(http_get: Mock) -> LocationController:
    return LocationController(api_key_getter=lambda: "test-key", http_get=http_get)


def test_lookup_demo_postcode_returns_validated_location() -> None:
    http_get = Mock()
    response = Mock()
    response.json.return_value = {
        "results": [
            {
                "postcode": "16802",
                "country_code": "us",
                "lat": 40.7934,
                "lon": -77.86,
                "city": "State College",
            }
        ]
    }
    http_get.return_value = response

    assert _controller(http_get).lookup_demo_postcode(" 16802 ") == {
        "postcode": "16802",
        "country_code": "us",
        "latitude": 40.7934,
        "longitude": -77.86,
        "locality": "State College",
    }
    http_get.assert_called_once_with(
        GEOAPIFY_FORWARD_GEOCODING_ENDPOINT,
        params={
            "text": DEMONSTRATION_POSTCODE,
            "type": "postcode",
            "filter": "countrycode:us",
            "format": "json",
            "limit": 1,
            "apiKey": "test-key",
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )


def test_lookup_demo_postcode_accepts_another_valid_zip() -> None:
    http_get = Mock()
    response = Mock()
    response.json.return_value = {
        "results": [
            {
                "postcode": "90210",
                "country_code": "us",
                "lat": 34.0901,
                "lon": -118.4065,
            }
        ]
    }
    http_get.return_value = response

    assert _controller(http_get).lookup_demo_postcode("90210") == {
        "postcode": "90210",
        "country_code": "us",
        "latitude": 34.0901,
        "longitude": -118.4065,
    }
    assert http_get.call_args.kwargs["params"]["text"] == "90210"


def test_lookup_demo_postcode_preserves_leading_zero() -> None:
    http_get = Mock()
    response = Mock()
    response.json.return_value = {
        "results": [
            {
                "postcode": "00501",
                "country_code": "us",
                "lat": 40.8136,
                "lon": -73.0464,
                "locality": "Holtsville",
            }
        ]
    }
    http_get.return_value = response

    assert _controller(http_get).lookup_demo_postcode("00501") == {
        "postcode": "00501",
        "country_code": "us",
        "latitude": 40.8136,
        "longitude": -73.0464,
        "locality": "Holtsville",
    }
    assert http_get.call_args.kwargs["params"]["text"] == "00501"


@pytest.mark.parametrize("invalid_zip", ["", "1234", "123456", "12A45", "12 45", "１２３４５"])
def test_lookup_demo_postcode_rejects_invalid_zip(invalid_zip: str) -> None:
    http_get = Mock()

    with pytest.raises(InvalidZipCodeError):
        _controller(http_get).lookup_demo_postcode(invalid_zip)

    http_get.assert_not_called()


def test_lookup_demo_postcode_rejects_mismatched_location() -> None:
    http_get = Mock()
    response = Mock()
    response.json.return_value = {
        "results": [
            {
                "postcode": "90210",
                "country_code": "us",
                "lat": 34.0736,
                "lon": -118.4004,
            }
        ]
    }
    http_get.return_value = response

    with pytest.raises(ZipLookupUnresolvedError):
        _controller(http_get).lookup_demo_postcode("16802")


def test_lookup_demo_postcode_hides_provider_failure_details() -> None:
    http_get = Mock(side_effect=httpx.TimeoutException("provider request failed"))

    with pytest.raises(ZipLookupProviderError, match="provider is unavailable") as error:
        _controller(http_get).lookup_demo_postcode("16802")

    assert "test-key" not in str(error.value)


def test_lookup_demo_postcode_rejects_missing_api_key() -> None:
    http_get = Mock()
    controller = LocationController(api_key_getter=lambda: None, http_get=http_get)

    with pytest.raises(ZipLookupConfigurationError):
        controller.lookup_demo_postcode("16802")

    http_get.assert_not_called()
