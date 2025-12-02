from __future__ import annotations

import pytest

from agent_api.http.rate_limit import ReducedScopeRateLimiter, ValkeyRateLimiterStub


@pytest.mark.asyncio
async def test_reduced_scope_rate_limiter_reports_demo_policy() -> None:
    limiter = ReducedScopeRateLimiter()
    await limiter.acquire(bucket="gpt", tokens=100)
    assert limiter.response_headers()["X-RateLimit-Policy"] == "demo-mode"
    assert limiter.sse_metadata()["rate_limit_disabled"] is True


def test_valkey_rate_limiter_stub_headers() -> None:
    limiter = ValkeyRateLimiterStub()
    assert limiter.response_headers()["X-RateLimit-Policy"] == "valkey"
