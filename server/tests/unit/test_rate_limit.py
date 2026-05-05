import time
import pytest
from ai_aid.rate_limit import SlidingWindow


def test_first_n_pass(monkeypatch):
    rl = SlidingWindow(limit=3, window_ms=60_000)
    monkeypatch.setattr("ai_aid.rate_limit._now_ms", lambda: 1000)
    assert rl.allow("alice") is True
    assert rl.allow("alice") is True
    assert rl.allow("alice") is True


def test_n_plus_one_blocked(monkeypatch):
    rl = SlidingWindow(limit=3, window_ms=60_000)
    monkeypatch.setattr("ai_aid.rate_limit._now_ms", lambda: 1000)
    for _ in range(3):
        rl.allow("alice")
    assert rl.allow("alice") is False


def test_clients_independent(monkeypatch):
    rl = SlidingWindow(limit=2, window_ms=60_000)
    monkeypatch.setattr("ai_aid.rate_limit._now_ms", lambda: 1000)
    rl.allow("alice")
    rl.allow("alice")
    assert rl.allow("alice") is False
    assert rl.allow("bob") is True


def test_window_expiry_releases_slots(monkeypatch):
    rl = SlidingWindow(limit=2, window_ms=1000)
    fake = {"t": 1000}
    monkeypatch.setattr("ai_aid.rate_limit._now_ms", lambda: fake["t"])
    rl.allow("alice")
    rl.allow("alice")
    assert rl.allow("alice") is False
    fake["t"] = 3000  # advance beyond window
    assert rl.allow("alice") is True
