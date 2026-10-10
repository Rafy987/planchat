import uuid
from types import SimpleNamespace

import psycopg
import pymupdf
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

import app.main
from app import extractor, llm, rate_limit
from app.config import settings
from app.main import app as fastapi_app
from app.rate_limit import DailyBudget, RateLimiter


class FakeClock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def client_from(ip: str) -> TestClient:
    return TestClient(fastapi_app, client=(ip, 50000))


# --- The sliding window itself ---


def test_allows_limit_then_blocks_until_oldest_request_leaves_window():
    clock = FakeClock()
    limiter = RateLimiter(limit=2, window_seconds=60, clock=clock)

    for _ in range(2):
        assert limiter.retry_after("1.1.1.1") == 0
        limiter.hit("1.1.1.1")
        clock.now += 10

    assert limiter.retry_after("1.1.1.1") == 40  # first request (t=1000) leaves at t=1060
    clock.now += 40
    assert limiter.retry_after("1.1.1.1") == 0


def test_each_ip_has_its_own_counter():
    limiter = RateLimiter(limit=1, window_seconds=60, clock=FakeClock())
    limiter.hit("1.1.1.1")

    assert limiter.retry_after("1.1.1.1") > 0
    assert limiter.retry_after("2.2.2.2") == 0


def test_old_entries_are_forgotten():
    clock = FakeClock()
    limiter = RateLimiter(limit=1, window_seconds=60, clock=clock)
    limiter.hit("1.1.1.1")
    clock.now += 61

    limiter.retry_after("1.1.1.1")

    assert limiter.hits == {}  # no memory kept for IPs that went quiet


def test_daily_budget_resets_on_a_new_day():
    clock = FakeClock(now=1_700_000_000)  # some moment on a UTC day
    budget = DailyBudget(limit=2, clock=clock)

    assert [budget.spend() for _ in range(3)] == [True, True, False]
    clock.now += 24 * 3600
    assert budget.spend() is True


@pytest.mark.parametrize("seconds, text", [(40, "40 seconds"), (119.2, "2 minutes"), (600, "10 minutes"), (20000, "6 hours")])
def test_wait_text(seconds, text):
    assert rate_limit._wait_text(seconds) == text


# --- Limits on the API (invalid requests still count, so no database is needed) ---


@pytest.fixture
def tiny_limits(monkeypatch):
    monkeypatch.setattr(settings, "ask_limit_per_minute", 2)
    monkeypatch.setattr(settings, "flooring_limit_per_hour", 1)
    monkeypatch.setattr(settings, "upload_limit_per_hour", 2)
    rate_limit.reset()  # pick up the new settings


def bad_ask(client: TestClient):
    return client.post("/ask", json={"document_id": "not-a-uuid", "question": "hi"})


def test_ask_is_blocked_after_the_limit_with_retry_after(tiny_limits):
    client = client_from("1.1.1.1")

    assert [bad_ask(client).status_code for _ in range(2)] == [422, 422]
    response = bad_ask(client)

    assert response.status_code == 429
    assert response.json()["detail"].startswith("Too many questions. Please wait")
    assert 0 < int(response.headers["retry-after"]) <= 60


def test_another_visitor_is_not_blocked(tiny_limits):
    for _ in range(3):
        bad_ask(client_from("1.1.1.1"))

    assert bad_ask(client_from("2.2.2.2")).status_code == 422  # not 429


def test_upload_limit(tiny_limits):
    client = client_from("1.1.1.1")
    upload = lambda: client.post("/documents", files={"file": ("a.pdf", b"", "application/pdf")})

    assert [upload().status_code for _ in range(3)] == [400, 400, 429]


def test_flooring_limit(tiny_limits):
    client = client_from("1.1.1.1")

    assert client.post("/documents/not-a-uuid/flooring").status_code == 422
    assert client.post("/documents/not-a-uuid/flooring").status_code == 429


def test_cheap_get_endpoints_are_not_limited(tiny_limits):
    client = client_from("1.1.1.1")

    assert all(client.get("/health").status_code == 200 for _ in range(20))


# --- App-wide daily budget of LLM calls ---


def test_llm_calls_stop_when_daily_budget_is_used_up(monkeypatch):
    monkeypatch.setattr(settings, "daily_llm_budget", 2)
    monkeypatch.setattr(settings, "groq_api_key", SecretStr("gsk_test"))
    monkeypatch.setattr(settings, "openai_api_key", None)
    rate_limit.reset()
    reply = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: reply))
    )
    monkeypatch.setattr(llm, "OpenAI", lambda **kw: fake_client)

    assert llm.complete("s", "u")["text"] == "ok"
    assert llm.complete("s", "u")["text"] == "ok"
    with pytest.raises(llm.LLMUnavailableError) as caught:
        llm.complete("s", "u")

    assert caught.value.message == llm.BUDGET_USED_UP


# --- Size caps ---


def test_pdf_with_too_many_pages_is_refused(monkeypatch):
    monkeypatch.setattr(settings, "max_pages", 2)
    doc = pymupdf.open()
    for _ in range(3):
        doc.new_page().insert_text((72, 72), "page")
    pdf_bytes = doc.tobytes()

    response = client_from("1.1.1.1").post(
        "/documents", files={"file": ("big.pdf", pdf_bytes, "application/pdf")}
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "PDF has 3 pages; the limit is 2."


def test_extractor_only_sends_capped_number_of_chunks(monkeypatch):
    monkeypatch.setattr(settings, "flooring_max_chunks", 1)
    sent = []
    monkeypatch.setattr(
        extractor.llm, "complete",
        lambda system, user, **kw: sent.append(user) or {"text": '{"items": []}'},
    )
    chunks = [
        {"chunk_index": 0, "page_number": 2, "text": "Room 101: LVP-1"},
        {"chunk_index": 1, "page_number": 9, "text": "Room 201: CPT-1"},
    ]

    result = extractor.extract_flooring(chunks)

    assert len(sent) == 1 and "CPT-1" not in sent[0]
    assert result["warnings"] == [
        "This document has a lot of flooring text; only pages up to 2 were scanned."
    ]


# --- Unexpected errors ---


def test_unexpected_error_gives_friendly_500_with_error_id(monkeypatch):
    def broken(document_id):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(app.main, "get_document", broken)

    response = client_from("1.1.1.1").get(
        f"/documents/{uuid.uuid4()}", headers={"Origin": "http://localhost:3000"}
    )

    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == (
        f"Something went wrong on our side. Please try again. (error ID {body['error_id']})"
    )
    assert "secret" not in response.text
    # CORS headers are still there, so the browser shows this message.
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_database_down_gives_503(monkeypatch):
    def db_down(document_id):
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(app.main, "get_document", db_down)

    response = client_from("1.1.1.1").get(f"/documents/{uuid.uuid4()}")

    assert response.status_code == 503
    assert response.json()["detail"].startswith("The database is temporarily unavailable")


# --- Real visitor IP behind a proxy (Render) ---


def ask_with_forwarded_for(header: str):
    return client_from("10.0.0.1").post(  # 10.0.0.1 = the proxy
        "/ask",
        json={"document_id": "not-a-uuid", "question": "hi"},
        headers={"X-Forwarded-For": header},
    )


def test_behind_proxy_a_faked_first_ip_does_not_bypass_the_limit(tiny_limits, monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_hops", 1)

    # The visitor sends a different fake IP each time; the proxy appends the real one.
    codes = [ask_with_forwarded_for(f"6.6.6.{i}, 1.1.1.1").status_code for i in range(3)]

    assert codes == [422, 422, 429]


def test_behind_proxy_different_real_visitors_are_separate(tiny_limits, monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_hops", 1)
    for _ in range(3):
        ask_with_forwarded_for("1.1.1.1")

    assert ask_with_forwarded_for("2.2.2.2").status_code == 422  # not blocked


def test_without_proxy_setting_the_header_is_ignored(tiny_limits):
    # Locally (hops=0) a visitor can't pick their own IP with this header.
    codes = [ask_with_forwarded_for(f"6.6.6.{i}").status_code for i in range(3)]

    assert codes == [422, 422, 429]
