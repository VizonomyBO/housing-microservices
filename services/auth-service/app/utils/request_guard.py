"""
Lightweight in-process request guard to replace external rate limiters.

This guard keeps per-identity counters in memory for small-scale quotas without
introducing cache backends. It is intentionally simple and should be paired with
upstream quotas when available.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from time import monotonic


@dataclass(frozen=True)
class GuardRule:
    """Guard rule describing max requests allowed within a window."""

    max_requests: int
    window_seconds: float


class SimpleRequestGuard:
    """In-memory request guard keyed by identity + scope."""

    def __init__(self, rules: dict[str, GuardRule]):
        self._rules = rules
        self._events: defaultdict[str, deque[float]] = defaultdict(deque)

    def allow(self, scope: str, identity: str) -> bool:
        """Return True if the request should proceed and record the attempt."""
        rule = self._rules.get(scope)
        if not rule:
            return True

        now = monotonic()
        key = f"{scope}:{identity}"
        events = self._events[key]
        self._prune(events, now, rule.window_seconds)

        if len(events) >= rule.max_requests:
            return False

        events.append(now)
        return True

    def reset(self) -> None:
        """Clear recorded events (useful for tests or process resets)."""
        self._events.clear()

    @staticmethod
    def _prune(events: deque[float], current: float, window_seconds: float) -> None:
        """Remove events older than the configured window."""
        while events and current - events[0] > window_seconds:
            events.popleft()
