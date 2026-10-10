"""Rate limiting: stop one visitor (or a script) from using up the Groq free tier.

Two layers:
- Per-IP limits on the expensive endpoints ("10 questions per minute").
- One daily budget of LLM calls for the WHOLE app, because one person can use
  many IP addresses.

Everything is kept in memory. That's fine for one small server: if it restarts,
the counters reset, but a server under attack stays awake, so they hold.
With several servers you would keep the counters in a shared store like Redis.
"""

import math
import threading
import time
from collections import deque
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from app.config import settings


class RateLimiter:
    """Sliding window: allow `limit` requests per `window_seconds` for each key (IP).

    Each key keeps the times of its recent requests; times older than the window
    drop off. If `limit` times are still inside the window, the request is refused.
    """

    def __init__(self, limit: int, window_seconds: float, clock=time.monotonic):
        self.limit = limit
        self.window = window_seconds
        self.clock = clock  # tests pass a fake clock
        self.hits: dict[str, deque] = {}

    def retry_after(self, key: str) -> float:
        """0 if `key` may make a request now, else seconds until it may."""
        now = self.clock()
        times = self.hits.get(key)
        if times is None:
            return 0
        while times and times[0] <= now - self.window:
            times.popleft()  # forget requests that left the window
        if not times:
            del self.hits[key]  # don't keep empty entries for every IP ever seen
            return 0
        if len(times) < self.limit:
            return 0
        return times[0] + self.window - now  # when the oldest one leaves the window

    def hit(self, key: str) -> None:
        self.hits.setdefault(key, deque()).append(self.clock())


class DailyBudget:
    """At most `limit` LLM calls per UTC day for the whole app."""

    def __init__(self, limit: int, clock=time.time):
        self.limit = limit
        self.clock = clock
        self.day = None
        self.used = 0

    def spend(self) -> bool:
        """Count one LLM call. False if today's budget is already used up."""
        today = datetime.fromtimestamp(self.clock(), timezone.utc).date()
        if today != self.day:  # a new day: start counting from zero again
            self.day, self.used = today, 0
        if self.used >= self.limit:
            return False
        self.used += 1
        return True


# Which limits apply to which action: (setting name, window in seconds, message).
LIMITS = {
    "ask": [
        ("ask_limit_per_minute", 60, "Too many questions"),
        ("ask_limit_per_day", 24 * 3600, "You've reached today's question limit"),
    ],
    "flooring": [("flooring_limit_per_hour", 3600, "Too many flooring extractions")],
    "upload": [("upload_limit_per_hour", 3600, "Too many uploads")],
}

_lock = threading.Lock()  # endpoints run in several threads at once
_limiters: dict[str, list[tuple[RateLimiter, str]]] = {}
_budget: DailyBudget | None = None


def _limiters_for(action: str) -> list[tuple[RateLimiter, str]]:
    if action not in _limiters:  # created on first use, from the current settings
        _limiters[action] = [
            (RateLimiter(getattr(settings, name), window), message)
            for name, window, message in LIMITS[action]
        ]
    return _limiters[action]


def _wait_text(seconds: float) -> str:
    seconds = math.ceil(seconds)
    if seconds < 120:
        return f"{seconds} seconds"
    if seconds < 2 * 3600:
        return f"{math.ceil(seconds / 60)} minutes"
    return f"{math.ceil(seconds / 3600)} hours"


def client_ip(request: Request) -> str:
    """The visitor's IP address.

    Behind a proxy (like Render's), every request comes FROM the proxy, and the
    real visitor IP is in the X-Forwarded-For header: "ip1, ip2, ..., ipN".
    Each proxy APPENDS the address it saw, so the last entries are trustworthy,
    but the first ones can be faked by the visitor (they can send their own
    header). With TRUSTED_PROXY_HOPS=1 we take the entry added by our one proxy.
    """
    hops = settings.trusted_proxy_hops
    if hops > 0:
        forwarded = request.headers.get("x-forwarded-for", "")
        hosts = [h.strip() for h in forwarded.split(",") if h.strip()]
        if len(hosts) >= hops:
            return hosts[-hops]
    return request.client.host if request.client else "unknown"


def check_rate_limit(action: str, request: Request) -> None:
    """Refuse with 429 if this visitor's IP is over any limit for `action`."""
    ip = client_ip(request)
    with _lock:
        limiters = _limiters_for(action)
        # Check every limit first, then count the request in all of them.
        for limiter, message in limiters:
            wait = limiter.retry_after(ip)
            if wait > 0:
                raise HTTPException(
                    status_code=429,
                    detail=f"{message}. Please wait {_wait_text(wait)} and try again.",
                    headers={"Retry-After": str(math.ceil(wait))},
                )
        for limiter, _ in limiters:
            limiter.hit(ip)


def rate_limit(action: str):
    """FastAPI dependency: `dependencies=[Depends(rate_limit("ask"))]`."""

    def dependency(request: Request) -> None:
        check_rate_limit(action, request)

    return dependency


def spend_llm_call() -> bool:
    """Count one LLM call against the app-wide daily budget."""
    global _budget
    with _lock:
        if _budget is None:
            _budget = DailyBudget(settings.daily_llm_budget)
        return _budget.spend()


def reset() -> None:
    """Forget all counters (used by tests, and picks up changed settings)."""
    global _budget
    with _lock:
        _limiters.clear()
        _budget = None
