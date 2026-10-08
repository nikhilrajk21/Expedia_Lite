"""Mocked checks for the basic backend-only chat integration."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.app import main
from backend.controllers.chat_controller import (
    ChatConfigurationError,
    ChatController,
    ChatProviderError,
    ChatValidationError,
)


class FakeResponses:
    def __init__(self, response_text: str = "Hello from the configured model.") -> None:
        self.response_text = response_text
        self.received_model = None
        self.received_input = None

    def create(self, *, model: str, input: str):
        self.received_model = model
        self.received_input = input
        return SimpleNamespace(output_text=self.response_text)


class FakeClient:
    def __init__(self, responses: FakeResponses, **kwargs) -> None:
        self.responses = responses
        self.received_options = kwargs


class StubChatController:
    def __init__(self, outcome: dict[str, str] | Exception) -> None:
        self.outcome = outcome
        self.received_message = None

    def reply(self, message: str) -> dict[str, str]:
        self.received_message = message
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def test_chat_controller_uses_configured_model_and_finite_timeout() -> None:
    responses = FakeResponses()
    client_options = {}

    def client_factory(**kwargs):
        client_options.update(kwargs)
        return FakeClient(responses, **kwargs)

    controller = ChatController(
        api_key_getter=lambda: "test-key",
        model_getter=lambda: "configured-model",
        client_factory=client_factory,
        timeout=12.0,
    )

    result = controller.reply("  Hello  ")

    assert result == {"reply": "Hello from the configured model."}
    assert responses.received_model == "configured-model"
    assert responses.received_input == "Hello"
    assert client_options == {"api_key": "test-key", "timeout": 12.0, "max_retries": 0}


def test_chat_controller_distinguishes_configuration_and_provider_failures() -> None:
    controller = ChatController(api_key_getter=lambda: None, model_getter=lambda: "model")
    try:
        controller.reply("Hello")
    except ChatConfigurationError:
        pass
    else:  # pragma: no cover - assertion branch
        raise AssertionError("Expected missing configuration to fail safely")

    class FailingResponses:
        def create(self, **_kwargs):
            raise RuntimeError("credential-bearing provider detail")

    class FailingClient:
        responses = FailingResponses()

    failing = ChatController(
        api_key_getter=lambda: "test-key",
        model_getter=lambda: "model",
        client_factory=lambda **_kwargs: FailingClient(),
    )
    try:
        failing.reply("Hello")
    except ChatProviderError as error:
        assert "credential-bearing" not in str(error)
    else:  # pragma: no cover - assertion branch
        raise AssertionError("Expected provider failure to be sanitized")


def test_chat_controller_rejects_blank_messages() -> None:
    controller = ChatController(api_key_getter=lambda: "test-key", model_getter=lambda: "model")

    try:
        controller.reply("   ")
    except ChatValidationError as error:
        assert str(error) == "Message cannot be empty."
    else:  # pragma: no cover - assertion branch
        raise AssertionError("Expected blank message validation")


def test_chat_route_returns_sanitized_reply(monkeypatch) -> None:
    controller = StubChatController({"reply": "Hello from the assistant."})
    monkeypatch.setattr(main, "chat_controller", controller, raising=False)

    response = TestClient(main.app).post("/api/chat", json={"message": "Hello"})

    assert response.status_code == 200
    assert response.json() == {"reply": "Hello from the assistant."}
    assert controller.received_message == "Hello"


def test_chat_route_returns_safe_errors(monkeypatch) -> None:
    cases = [
        (ChatConfigurationError("secret value"), 503, "Chat is not configured."),
        (ChatProviderError("secret value"), 502, "Chat provider is unavailable."),
        (ChatValidationError("secret value"), 400, "Message cannot be empty or too long."),
    ]

    for error, expected_status, expected_detail in cases:
        monkeypatch.setattr(
            main, "chat_controller", StubChatController(error), raising=False
        )
        response = TestClient(main.app).post("/api/chat", json={"message": "Hello"})

        assert response.status_code == expected_status
        assert response.json() == {"detail": expected_detail}
        assert "secret value" not in response.text


def test_chat_route_accepts_conversation_id(monkeypatch) -> None:
    class ConversationAwareStub:
        def __init__(self):
            self.received_id = None

        def reply(self, message: str, conversation_id: str | None = None):
            self.received_id = conversation_id
            return {"conversation_id": conversation_id, "reply": message}

    controller = ConversationAwareStub()
    monkeypatch.setattr(main, "chat_controller", controller, raising=False)
    conversation_id = "4e3f0e34-5d4c-4e3d-8c1e-6bc11ab87000"

    response = TestClient(main.app).post(
        "/api/chat",
        json={"message": "Hello", "conversation_id": conversation_id},
    )

    assert response.status_code == 200
    assert response.json() == {"conversation_id": conversation_id, "reply": "Hello"}
    assert controller.received_id == conversation_id


def test_chat_history_route_returns_labeled_messages(monkeypatch) -> None:
    class ConversationHistoryStub:
        def normalize_id(self, conversation_id):
            return conversation_id

        def history(self, conversation_id):
            return [
                {
                    "message_id": "m1",
                    "conversation_id": conversation_id,
                    "timestamp": "2026-10-08T00:00:00+00:00",
                    "role": "user",
                    "stage": "user_question",
                    "content": "Hello",
                }
            ]

    monkeypatch.setattr(main, "conversation_controller", ConversationHistoryStub())
    conversation_id = "4e3f0e34-5d4c-4e3d-8c1e-6bc11ab87000"

    response = TestClient(main.app).get(
        "/api/chat/history", params={"conversation_id": conversation_id}
    )

    assert response.status_code == 200
    assert response.json()["messages"][0]["stage"] == "user_question"
