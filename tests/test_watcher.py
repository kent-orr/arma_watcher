"""
Tests for arma_watcher/watcher.py.

State-init and rate-calculation tests are pure unit tests (no ollama, no display).
"""
import threading
import time
import types
from datetime import datetime, timedelta

import pytest

from arma_watcher.inference import CloudRateLimitError
from arma_watcher.watcher import (
    _FRONT_OF_QUEUE_TIMEOUT_S,
    _MAX_ARMA_ATTEMPTS,
    ArmaWatcher,
    QueueEntry,
    WatcherState,
    _WatcherStopped,
)


def _history(pairs: list[tuple[int, float]]) -> list[QueueEntry]:
    """Build a QueueEntry list from (position, minutes_offset) pairs."""
    base = datetime(2024, 1, 1, 12, 0, 0)
    return [QueueEntry(base + timedelta(minutes=offset), pos) for pos, offset in pairs]


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------


class TestArmaWatcherInit:
    def test_explicit_monitor_starts_in_searching_queue(self):
        assert ArmaWatcher(monitor_index=1).state == WatcherState.SEARCHING_QUEUE

    def test_no_monitor_starts_in_searching_arma(self):
        assert ArmaWatcher().state == WatcherState.SEARCHING_ARMA

    def test_explicit_monitor_stored(self):
        assert ArmaWatcher(monitor_index=2).monitor_index == 2

    def test_no_monitor_stored_as_none(self):
        assert ArmaWatcher().monitor_index is None

    def test_history_empty_on_init(self):
        assert ArmaWatcher(monitor_index=1).history == []

    def test_server_name_none_on_init(self):
        assert ArmaWatcher(monitor_index=1).server_name is None

    def test_default_queue_interval(self):
        assert ArmaWatcher(monitor_index=1).queue_interval == 20

    def test_custom_queue_interval(self):
        assert ArmaWatcher(monitor_index=1, queue_interval=60).queue_interval == 60

    def test_default_detect_interval(self):
        assert ArmaWatcher(monitor_index=1).detect_interval == 5


# ---------------------------------------------------------------------------
# Rate and ETA calculations (pure math — no ollama, no display)
# ---------------------------------------------------------------------------


class TestArmaWatcherRateCalc:
    def test_avg_rate_no_history_returns_none(self):
        assert ArmaWatcher(monitor_index=1)._avg_rate() is None

    def test_avg_rate_one_entry_returns_none(self):
        w = ArmaWatcher(monitor_index=1)
        w.history = _history([(10, 0)])
        assert w._avg_rate() is None

    def test_avg_rate_two_entries_same_time_returns_none(self):
        w = ArmaWatcher(monitor_index=1)
        w.history = _history([(10, 0), (8, 0)])
        assert w._avg_rate() is None

    def test_avg_rate_two_entries(self):
        # dropped 10 positions in 10 minutes → 1.0/min
        w = ArmaWatcher(monitor_index=1)
        w.history = _history([(20, 0), (10, 10)])
        assert w._avg_rate() == pytest.approx(1.0)

    def test_avg_rate_multiple_entries_uses_first_and_last(self):
        # 30 → 20 → 10 over 20 min → 1.0/min (ignores middle)
        w = ArmaWatcher(monitor_index=1)
        w.history = _history([(30, 0), (20, 10), (10, 20)])
        assert w._avg_rate() == pytest.approx(1.0)

    def test_avg_rate_negative_movement_is_negative(self):
        # position went up — re-queued or glitch
        w = ArmaWatcher(monitor_index=1)
        w.history = _history([(5, 0), (10, 5)])
        assert w._avg_rate() is not None
        assert w._avg_rate() < 0  # type: ignore[operator]

    def test_predicted_minutes_no_history_returns_none(self):
        assert ArmaWatcher(monitor_index=1)._predicted_minutes() is None

    def test_predicted_minutes_with_rate(self):
        # 1.0/min rate, current position 5 → 5 min ETA
        w = ArmaWatcher(monitor_index=1)
        w.history = _history([(10, 0), (5, 5)])
        assert w._predicted_minutes() == pytest.approx(5.0)

    def test_predicted_minutes_zero_rate_returns_none(self):
        w = ArmaWatcher(monitor_index=1)
        w.history = _history([(10, 0), (10, 5)])
        assert w._predicted_minutes() is None

    def test_predicted_minutes_negative_rate_returns_none(self):
        w = ArmaWatcher(monitor_index=1)
        w.history = _history([(5, 0), (10, 5)])
        assert w._predicted_minutes() is None


# ---------------------------------------------------------------------------
# Interruptible retry backoff (Stop must not block on the 60s rate-limit wait)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Give up scanning for Arma after a fixed number of attempts (no backoff loop)
# ---------------------------------------------------------------------------


class TestArmaDetectionGiveUp:
    def _watcher(self, monkeypatch, *, found: bool):
        # SEARCHING_ARMA (no monitor), zero detect interval so retries don't sleep.
        w = ArmaWatcher(detect_interval=0)
        w._inference = types.SimpleNamespace(is_arma=lambda _b: found)
        monkeypatch.setattr("arma_watcher.watcher.list_monitors", lambda: [0, 1, 2])
        monkeypatch.setattr("arma_watcher.watcher.capture_to_bytes", lambda _i: b"")
        return w

    def test_gives_up_after_max_attempts(self, monkeypatch):
        w = self._watcher(monkeypatch, found=False)
        for _ in range(_MAX_ARMA_ATTEMPTS):
            w._step_searching_arma()
        assert w._stop.is_set()
        assert w._stop_reason is not None
        assert "Couldn't find Arma" in w._stop_reason

    def test_does_not_give_up_before_max(self, monkeypatch):
        w = self._watcher(monkeypatch, found=False)
        for _ in range(_MAX_ARMA_ATTEMPTS - 1):
            w._step_searching_arma()
        assert not w._stop.is_set()
        assert w._stop_reason is None

    def test_found_arma_advances_without_stopping(self, monkeypatch):
        w = self._watcher(monkeypatch, found=True)
        w._step_searching_arma()
        assert w.state == WatcherState.SEARCHING_QUEUE
        assert not w._stop.is_set()
        assert w.monitor_index == 1


# ---------------------------------------------------------------------------
# Front-of-queue timeout — assume in-game if stuck at the front too long
# ---------------------------------------------------------------------------


class TestFrontOfQueueTimeout:
    def test_record_starts_front_clock_at_position_one(self):
        w = ArmaWatcher(monitor_index=1)
        w._record(5)
        assert w._front_of_queue_at is None
        w._record(1)
        assert w._front_of_queue_at is not None

    def test_record_front_clock_set_only_once(self):
        w = ArmaWatcher(monitor_index=1)
        w._record(1)
        first = w._front_of_queue_at
        w._record(0)  # position 0 also counts as the front, but clock stays put
        assert w._front_of_queue_at == first

    def test_not_timed_out_before_reaching_front(self):
        assert ArmaWatcher(monitor_index=1)._front_of_queue_timed_out() is False

    def test_not_timed_out_within_window(self):
        w = ArmaWatcher(monitor_index=1)
        w._front_of_queue_at = datetime.now() - timedelta(seconds=_FRONT_OF_QUEUE_TIMEOUT_S - 60)
        assert w._front_of_queue_timed_out() is False

    def test_timed_out_after_window(self):
        w = ArmaWatcher(monitor_index=1)
        w._front_of_queue_at = datetime.now() - timedelta(seconds=_FRONT_OF_QUEUE_TIMEOUT_S + 60)
        assert w._front_of_queue_timed_out() is True

    def test_end_timeout_stops_with_reason(self):
        w = ArmaWatcher(monitor_index=1)
        w._end_front_of_queue_timeout()
        assert w._stop.is_set()
        assert w._stop_reason is not None
        assert "front of the queue" in w._stop_reason


class TestArmaWatcherBackoff:
    def test_backoff_returns_after_timeout_when_not_stopped(self):
        w = ArmaWatcher(monitor_index=1)
        start = time.monotonic()
        assert w._backoff(0.02) is None
        assert time.monotonic() - start < 1.0

    def test_backoff_raises_immediately_when_already_stopped(self):
        w = ArmaWatcher(monitor_index=1)
        w.stop()
        start = time.monotonic()
        with pytest.raises(_WatcherStopped):
            w._backoff(60)  # would block a full minute without the stop event
        assert time.monotonic() - start < 1.0

    def test_infer_call_aborts_rate_limit_backoff_on_stop(self):
        """A 429 backoff must unwind the moment stop() is called, not after 60s."""
        w = ArmaWatcher(monitor_index=1)

        def always_rate_limited():
            raise CloudRateLimitError("rate limited by inference proxy")

        threading.Timer(0.05, w.stop).start()
        start = time.monotonic()
        with pytest.raises(_WatcherStopped):
            w._infer_call(always_rate_limited)
        assert time.monotonic() - start < 5.0
