from types import SimpleNamespace

import httpx
import openai
import pytest
from pydantic import SecretStr

from app import llm
from app.config import settings

REQUEST = httpx.Request("POST", "https://example.test/chat/completions")


def status_error(cls, status: int, message: str = "error"):
    return cls(message, response=httpx.Response(status, request=REQUEST), body=None)


class FakeLLM:
    """Replaces the OpenAI client. `replies[provider]` is a text or an exception."""

    def __init__(self):
        self.replies = {}
        self.calls = []  # which providers were called, in order

    def client(self, api_key, base_url, timeout, max_retries):
        provider = "groq" if base_url and "groq" in base_url else "openai"

        def create(**kwargs):
            self.calls.append(provider)
            reply = self.replies[provider]
            if isinstance(reply, Exception):
                raise reply
            message = SimpleNamespace(content=reply)
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


@pytest.fixture
def fake(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(llm, "OpenAI", fake.client)
    monkeypatch.setattr(settings, "llm_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", SecretStr("gsk_test"))
    monkeypatch.setattr(settings, "openai_api_key", SecretStr("sk_test"))
    return fake


def test_main_provider_answers(fake):
    fake.replies = {"groq": "Carpet [p. 2]", "openai": "unused"}

    result = llm.complete("system", "user")

    assert result == {"text": "Carpet [p. 2]", "provider": "groq", "model": settings.groq_model}
    assert fake.calls == ["groq"]


@pytest.mark.parametrize(
    "error",
    [
        status_error(openai.RateLimitError, 429),
        status_error(openai.APIStatusError, 413),  # Groq: over tokens-per-minute
        status_error(openai.BadRequestError, 400, "context_length_exceeded"),
        status_error(openai.InternalServerError, 503),
        openai.APITimeoutError(request=REQUEST),
        openai.APIConnectionError(request=REQUEST),
    ],
    ids=["rate-limit", "token-limit", "context-too-long", "server-error", "timeout", "no-connection"],
)
def test_falls_back_to_other_provider(fake, error):
    fake.replies = {"groq": error, "openai": "Carpet [p. 2]"}

    result = llm.complete("system", "user")

    assert result["provider"] == "openai"
    assert fake.calls == ["groq", "openai"]


def test_no_fallback_without_other_key_gives_friendly_error(fake, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", SecretStr("PASTE_HERE"))  # placeholder
    fake.replies = {"groq": status_error(openai.RateLimitError, 429)}

    with pytest.raises(llm.LLMUnavailableError) as caught:
        llm.complete("system", "user")

    assert "busy" in caught.value.message
    assert fake.calls == ["groq"]


def test_both_providers_failing_gives_friendly_error(fake):
    fake.replies = {
        "groq": status_error(openai.RateLimitError, 429),
        "openai": openai.APITimeoutError(request=REQUEST),
    }

    with pytest.raises(llm.LLMUnavailableError) as caught:
        llm.complete("system", "user")

    assert "temporarily unavailable" in caught.value.message
    assert fake.calls == ["groq", "openai"]


def test_wrong_api_key_is_not_hidden_by_fallback(fake):
    fake.replies = {"groq": status_error(openai.AuthenticationError, 401), "openai": "unused"}

    with pytest.raises(openai.AuthenticationError):
        llm.complete("system", "user")
    assert fake.calls == ["groq"]


def test_openai_can_be_the_main_provider(fake, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    fake.replies = {"openai": "answer", "groq": "unused"}

    assert llm.complete("system", "user")["provider"] == "openai"


def test_no_keys_at_all_gives_friendly_error(fake, monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", None)
    monkeypatch.setattr(settings, "openai_api_key", SecretStr(""))

    with pytest.raises(llm.LLMUnavailableError, match="not configured"):
        llm.complete("system", "user")


def test_hidden_thinking_is_removed(fake):
    fake.replies = {"groq": "<think>let me look...</think>\nCarpet [p. 2]"}

    assert llm.complete("system", "user")["text"] == "Carpet [p. 2]"


def test_api_keys_are_hidden_when_settings_are_printed(fake):
    assert "gsk_test" not in str(settings)
    assert "gsk_test" not in repr(settings)
