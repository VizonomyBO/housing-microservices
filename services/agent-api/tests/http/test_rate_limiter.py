from __future__ import annotations

import pytest

from agent_api.http.rate_limit import BypassRateLimiter


@pytest.mark.asyncio
async def test_bypass_rate_limiter_reports_demo_policy() -> None:
    limiter = BypassRateLimiter()
    await limiter.acquire(bucket="gpt", tokens=100)
    assert limiter.response_headers()["X-RateLimit-Policy"] == "bypass"
    assert limiter.sse_metadata()["rate_limit_disabled"] is True
