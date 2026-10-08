"""Route contract tests for local saved-provider-hotel operations."""

from fastapi.testclient import TestClient

from backend.app import main
from backend.controllers.saved_hotel_controller import (
    SavedHotelNotFoundError,
    SavedHotelPersistenceError,
    SavedHotelValidationError,
)


class StubSavedHotelController:
    def __init__(self, save_outcome=None, list_outcome=None, remove_outcome=None):
        self.save_outcome = save_outcome
        self.list_outcome = list_outcome
        self.remove_outcome = remove_outcome
        self.saved_request = None
        self.listed_zip = None
        self.removed_id = None

    def save(self, request):
        self.saved_request = request
        if isinstance(self.save_outcome, Exception):
            raise self.save_outcome
        return self.save_outcome

    def list_for_zip(self, zip_code):
        self.listed_zip = zip_code
        if isinstance(self.list_outcome, Exception):
            raise self.list_outcome
        return self.list_outcome

    def remove(self, hotel_id):
        self.removed_id = hotel_id
        if isinstance(self.remove_outcome, Exception):
            raise self.remove_outcome


def _payload() -> dict[str, object]:
    return {
        "place_id": "provider-1",
        "name": "Provider Hotel",
        "address": "1 Main Street",
        "latitude": 40.0,
        "longitude": -77.0,
        "zip_code": "00501",
        "center": {"latitude": 40.1, "longitude": -77.1},
    }


def test_saved_hotel_routes_preserve_request_and_response(monkeypatch) -> None:
    expected_save = {
        "hotel": {"place_id": "provider-1", "name": "Provider Hotel"},
        "location": {"zip_code": "00501"},
        "nights": [],
    }
    controller = StubSavedHotelController(expected_save, [_payload()])
    monkeypatch.setattr(main, "saved_hotel_controller", controller, raising=False)

    save_response = TestClient(main.app).post("/api/saved-hotels", json=_payload())
    list_response = TestClient(main.app).get("/api/saved-hotels?zip_code=00501")
    delete_response = TestClient(main.app).delete("/api/saved-hotels/provider-1")

    assert save_response.status_code == 201
    assert save_response.json() == expected_save
    assert controller.saved_request["place_id"] == "provider-1"
    assert controller.saved_request["zip_code"] == "00501"
    assert list_response.status_code == 200
    assert list_response.json() == {"results": [_payload()]}
    assert controller.listed_zip == "00501"
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted_place_id": "provider-1"}
    assert controller.removed_id == "provider-1"


def test_saved_hotel_routes_return_safe_errors(monkeypatch) -> None:
    cases = [
        (SavedHotelValidationError("secret value"), 400, "secret value"),
        (SavedHotelPersistenceError("secret value"), 500, "Saved hotel could not be stored."),
    ]
    for error, expected_status, expected_detail in cases:
        controller = StubSavedHotelController(save_outcome=error)
        monkeypatch.setattr(main, "saved_hotel_controller", controller, raising=False)
        response = TestClient(main.app).post("/api/saved-hotels", json=_payload())
        assert response.status_code == expected_status
        if expected_status == 400:
            assert response.json() == {"detail": "secret value"}
        else:
            assert response.json() == {"detail": expected_detail}
        if expected_status == 500:
            assert "secret value" not in response.text

    controller = StubSavedHotelController(
        list_outcome=SavedHotelValidationError("secret value")
    )
    monkeypatch.setattr(main, "saved_hotel_controller", controller, raising=False)
    response = TestClient(main.app).get("/api/saved-hotels?zip_code=bad")
    assert response.status_code == 400
    assert "secret value" in response.text

    controller = StubSavedHotelController(
        remove_outcome=SavedHotelNotFoundError("secret value")
    )
    monkeypatch.setattr(main, "saved_hotel_controller", controller, raising=False)
    response = TestClient(main.app).delete("/api/saved-hotels/provider-1")
    assert response.status_code == 404
    assert response.json() == {"detail": "Saved hotel was not found."}
    assert "secret value" not in response.text
