"""Unit tests for the lightweight request guard."""

import time

from app.utils.request_guard import GuardRule, SimpleRequestGuard


def test_guard_blocks_after_limit():
    guard = SimpleRequestGuard({"login": GuardRule(max_requests=2, window_seconds=10)})

    assert guard.allow("login", "client-1")
    assert guard.allow("login", "client-1")
    assert not guard.allow("login", "client-1")


def test_guard_resets_after_window():
    guard = SimpleRequestGuard({"reset": GuardRule(max_requests=1, window_seconds=0.01)})

    assert guard.allow("reset", "client-2")
    assert not guard.allow("reset", "client-2")
    time.sleep(0.02)
    assert guard.allow("reset", "client-2")


def test_guard_reset_method_clears_events():
    guard = SimpleRequestGuard({"refresh": GuardRule(max_requests=1, window_seconds=60)})

    assert guard.allow("refresh", "client-3")
    assert not guard.allow("refresh", "client-3")
    guard.reset()
    assert guard.allow("refresh", "client-3")
