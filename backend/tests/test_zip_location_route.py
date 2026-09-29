"""Mocked route checks for the backend-only ZIP demonstration."""

from fastapi.testclient import TestClient

from backend.app import main
from backend.controllers.location_controller import (
    InvalidZipCodeError,
    ZipLookupConfigurationError,
    ZipLookupProviderError,
    ZipLookupUnresolvedError,
)
from backend.controllers.nearby_hotel_controller import (
    NearbyHotelInvalidDataError,
    NearbyHotelNoResultsError,
    NearbyHotelProviderError,
)


class StubLocationController:
    def __init__(self, outcome: dict[str, object] | Exception) -> None:
        self._outcome = outcome

    def lookup_demo_postcode(self, zip_code: str) -> dict[str, object]:
        self.received_zip = zip_code
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


class StubNearbyHotelController:
    def __init__(self, outcome: list[dict[str, object]] | Exception) -> None:
        self._outcome = outcome
        self.received_zip = None
        self.received_location = None

    def find_nearby_hotels(self, zip_code: str) -> list[dict[str, object]]:
        self.received_zip = zip_code
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome

    def find_nearby_hotels_at_location(
        self, location: dict[str, object]
    ) -> list[dict[str, object]]:
        self.received_location = location
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


def test_demo_zip_location_returns_controller_response(monkeypatch) -> None:
    expected_location = {
        "postcode": "16802",
        "country_code": "us",
        "latitude": 40.0,
        "longitude": -77.0,
    }
    controller = StubLocationController(expected_location)
    monkeypatch.setattr(main, "location_controller", controller, raising=False)

    response = TestClient(main.app).get("/api/demo/zip-location?zip_code=16802")

    assert response.status_code == 200
    assert response.json() == expected_location
    assert controller.received_zip == "16802"


def test_demo_zip_location_returns_safe_errors(monkeypatch) -> None:
    cases = [
        (InvalidZipCodeError("secret value"), 400, "ZIP code must be exactly five ASCII digits."),
        (ZipLookupConfigurationError("secret value"), 503, "ZIP lookup is not configured."),
        (ZipLookupUnresolvedError("secret value"), 404, "Requested ZIP code could not be resolved."),
        (ZipLookupProviderError("secret value"), 502, "ZIP lookup provider is unavailable."),
    ]

    for error, expected_status, expected_detail in cases:
        monkeypatch.setattr(
            main, "location_controller", StubLocationController(error), raising=False
        )

        response = TestClient(main.app).get("/api/demo/zip-location?zip_code=16802")

        assert response.status_code == expected_status
        assert response.json() == {"detail": expected_detail}
        assert "secret value" not in response.text


def test_nearby_hotels_route_returns_sanitized_results(monkeypatch) -> None:
    expected_results = [
        {
            "place_id": "provider-place-1",
            "name": "Provider Hotel",
            "address": "1 Main Street",
            "latitude": 40.804,
            "longitude": -77.862,
        }
    ]
    controller = StubNearbyHotelController(expected_results)
    monkeypatch.setattr(main, "nearby_hotel_controller", controller, raising=False)

    response = TestClient(main.app).get("/api/demo/nearby-hotels?zip_code=16802")

    assert response.status_code == 200
    assert response.json() == {"results": expected_results}
    assert controller.received_zip == "16802"


def test_nearby_hotels_route_distinguishes_no_results_and_provider_failure(monkeypatch) -> None:
    cases = [
        (NearbyHotelNoResultsError("secret value"), 404, "No hotels were found near the requested ZIP."),
        (NearbyHotelProviderError("secret value"), 502, "Nearby hotel provider is unavailable."),
    ]

    for error, expected_status, expected_detail in cases:
        monkeypatch.setattr(
            main, "nearby_hotel_controller", StubNearbyHotelController(error), raising=False
        )

        response = TestClient(main.app).get("/api/demo/nearby-hotels?zip_code=16802")

        assert response.status_code == expected_status
        assert response.json() == {"detail": expected_detail}
        assert "secret value" not in response.text


def test_hotels_nearby_route_returns_center_and_sanitized_results(monkeypatch) -> None:
    expected_location = {
        "postcode": "16802",
        "country_code": "us",
        "latitude": 40.0,
        "longitude": -77.0,
        "locality": "State College",
    }
    expected_results = [
        {
            "place_id": "provider-place-1",
            "name": "Provider Hotel",
            "address": "1 Main Street",
            "latitude": 40.004,
            "longitude": -77.002,
        }
    ]
    location_controller = StubLocationController(expected_location)
    nearby_controller = StubNearbyHotelController(expected_results)
    monkeypatch.setattr(main, "location_controller", location_controller, raising=False)
    monkeypatch.setattr(main, "nearby_hotel_controller", nearby_controller, raising=False)

    response = TestClient(main.app).get("/api/hotels/nearby?zip_code=16802")

    assert response.status_code == 200
    assert response.json() == {
        "zip_code": "16802",
        "center": {"latitude": 40.0, "longitude": -77.0},
        "results": expected_results,
    }
    assert location_controller.received_zip == "16802"
    assert nearby_controller.received_location == expected_location


def test_hotels_nearby_route_distinguishes_zip_and_provider_errors(monkeypatch) -> None:
    location_cases = [
        (InvalidZipCodeError("secret value"), 400, "ZIP code must be exactly five ASCII digits."),
        (ZipLookupConfigurationError("secret value"), 503, "ZIP lookup is not configured."),
        (ZipLookupUnresolvedError("secret value"), 404, "Requested ZIP code could not be resolved."),
        (ZipLookupProviderError("secret value"), 502, "ZIP lookup provider is unavailable."),
    ]
    for error, expected_status, expected_detail in location_cases:
        monkeypatch.setattr(
            main, "location_controller", StubLocationController(error), raising=False
        )
        response = TestClient(main.app).get("/api/hotels/nearby?zip_code=16802")
        assert response.status_code == expected_status
        assert response.json() == {"detail": expected_detail}
        assert "secret value" not in response.text

    for error, expected_status, expected_detail in [
        (NearbyHotelNoResultsError("secret value"), 404, "No hotels were found near the requested ZIP."),
        (NearbyHotelInvalidDataError("secret value"), 502, "Nearby hotel provider returned incomplete hotel data."),
        (NearbyHotelProviderError("secret value"), 502, "Nearby hotel provider is unavailable."),
    ]:
        monkeypatch.setattr(
            main,
            "location_controller",
            StubLocationController(
                {
                    "postcode": "16802",
                    "country_code": "us",
                    "latitude": 40.0,
                    "longitude": -77.0,
                }
            ),
            raising=False,
        )
        monkeypatch.setattr(
            main, "nearby_hotel_controller", StubNearbyHotelController(error), raising=False
        )
        response = TestClient(main.app).get("/api/hotels/nearby?zip_code=16802")
        assert response.status_code == expected_status
        assert response.json() == {"detail": expected_detail}
        assert "secret value" not in response.text
