import logging
import re
import time

import openai
from openai import OpenAI

from app.config import settings

# Groq offers an OpenAI-compatible API, so one library (openai) talks to both.
# Only the base URL, key and model differ.
BASE_URLS = {"groq": "https://api.groq.com/openai/v1", "openai": None}

logger = logging.getLogger(__name__)


class LLMUnavailableError(Exception):
    """The LLM can't answer right now. `message` is safe to show to users."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _api_key(provider: str) -> str | None:
    secret = settings.groq_api_key if provider == "groq" else settings.openai_api_key
    key = secret.get_secret_value().strip() if secret else ""
    # An empty key or the .env placeholder means "not configured".
    return key if key and key != "PASTE_HERE" else None


def _model(provider: str) -> str:
    return settings.groq_model if provider == "groq" else settings.openai_model


def _providers_to_try() -> list[str]:
    """Main provider first, then the other one as fallback - only those with a key."""
    main = settings.llm_provider
    other = "openai" if main == "groq" else "groq"
    return [p for p in (main, other) if _api_key(p)]


def _friendly_message(error: Exception) -> str | None:
    """Return a user-friendly message if this error is worth a fallback, else None."""
    if isinstance(error, openai.RateLimitError):  # 429: too many requests / tokens
        return "The AI service is busy right now (rate limit). Please try again in a minute."
    if isinstance(error, openai.APIStatusError) and error.status_code == 413:
        # Groq uses 413 when a request is over the tokens-per-minute limit.
        return "The AI service is busy right now (token limit). Please try again in a minute."
    if isinstance(error, openai.BadRequestError) and "context" in str(error).lower():
        return "The question and document excerpts were too long for the AI model."
    if isinstance(error, (openai.APIConnectionError, openai.InternalServerError)):
        # APIConnectionError includes timeouts; InternalServerError is any 5xx.
        return "The AI service is temporarily unavailable. Please try again shortly."
    return None


DEFAULT_RATE_LIMIT_WAIT = 10.0  # seconds, when a 429 doesn't say how long to wait


def _retry_after_seconds(error: Exception) -> float | None:
    """For a rate limit (429), how long to wait: what the provider asks, else 10 s."""
    if not isinstance(error, openai.RateLimitError):
        return None
    try:
        return float(error.response.headers.get("retry-after"))
    except (TypeError, ValueError):
        return DEFAULT_RATE_LIMIT_WAIT


def complete(
    system: str,
    user: str,
    *,
    json_mode: bool = False,
    max_tokens: int | None = None,
    max_wait_seconds: float = 0,
) -> dict:
    """Send a prompt to the LLM, falling back to the other provider on limits/outages.

    json_mode: ask the model to reply with valid JSON only.
    max_wait_seconds: on a rate limit, wait as long as the provider asks (up to this
        many seconds in total) and try the same provider again. Chat questions use 0
        (fail fast); long jobs like the flooring extractor can afford to wait.

    Returns {"text", "provider", "model"}. Raises LLMUnavailableError with a
    friendly message if no provider could answer.
    """
    providers = _providers_to_try()
    if not providers:
        raise LLMUnavailableError("The AI service is not configured (no API key set).")

    extra = {"response_format": {"type": "json_object"}} if json_mode else {}
    message = None
    for provider in providers:
        # max_retries=0: don't let the library retry the same provider again and
        # again; on a limit or outage we'd rather switch to the other provider.
        client = OpenAI(
            api_key=_api_key(provider),
            base_url=BASE_URLS[provider],
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )
        waited = 0.0
        while True:
            try:
                response = client.chat.completions.create(
                    model=_model(provider),
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=0,  # factual answers: same question -> same answer
                    max_tokens=max_tokens or settings.llm_max_tokens,
                    **extra,
                )
            except openai.APIError as error:
                # Log what went wrong (never the key) so problems can be diagnosed.
                logger.warning("LLM call to %s failed: %s", provider, error)
                wait = _retry_after_seconds(error)
                if wait is not None and waited + wait <= max_wait_seconds:
                    time.sleep(wait)  # the provider told us when we may try again
                    waited += wait
                    continue
                message = _friendly_message(error)
                if message is None:
                    raise  # e.g. a wrong API key: a real bug, don't hide it
                break  # try the next provider

            text = response.choices[0].message.content or ""
            # Some models write hidden "thinking" in <think> tags; users shouldn't see it.
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            return {"text": text, "provider": provider, "model": _model(provider)}

    raise LLMUnavailableError(message)
