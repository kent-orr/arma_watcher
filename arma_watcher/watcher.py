import json
import threading
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TypeVar

_T = TypeVar("_T")

import ollama

from arma_watcher.inference import (
    CloudAuthError,
    CloudRateLimitError,
    MODEL,
    ScreenState,
    ensure_model,
    make_inference,
)
from arma_watcher.screenshot import capture_to_bytes, list_monitors


def _notify_discord(url: str, msg: str) -> bool:
    data = json.dumps({"content": msg}).encode()
    req = urllib.request.Request(
        url, data,
        {"Content-Type": "application/json", "User-Agent": "ArmaWatcher/1.0"},
    )
    try:
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception as e:
        masked = url[:40] + "..." if len(url) > 40 else url
        print(f"[discord] failed to send notification — {type(e).__name__}: {e}")
        print(f"[discord] webhook: {masked}")
        print(f"[discord] message attempted: {msg!r}")
        return False


class _WatcherStopped(Exception):
    """Internal signal: stop() was called mid-retry — unwind to the graceful
    shutdown tail in run() instead of finishing the current backoff."""


class WatcherState(Enum):
    SEARCHING_ARMA = "searching_arma"
    SEARCHING_QUEUE = "searching_queue"
    IN_QUEUE = "in_queue"
    IN_GAME = "in_game"


@dataclass
class QueueEntry:
    timestamp: datetime
    position: int


@dataclass
class MessagePlan:
    message_ints: list[int]  # positions to notify at (descending)
    messages: list[str]      # one message per threshold, same order


# Give up scanning for Arma after this many full monitor sweeps — if the game
# isn't up yet, retrying forever just burns the user's GPU/credits silently.
_MAX_ARMA_ATTEMPTS = 5

# Once the queue reaches the front (position 1), the game normally loads within a
# minute or two. If we sit at the front this long without ever detecting the
# in-game screen, the user is almost certainly in but we missed the transition —
# stop instead of polling indefinitely.
_FRONT_OF_QUEUE_TIMEOUT_S = 15 * 60


_MILESTONES = [
    (30, "Still waiting — 30 to go."),
    (20, "Getting closer — 20 to go."),
    (10, "Only 10 left!"),
    (5,  "Almost there — 5 to go!"),
    (3,  "3 more!"),
    (1,  "Next up!"),
]


def _default_message_plan(initial_position: int) -> MessagePlan:
    pairs = [(pos, msg) for pos, msg in _MILESTONES if pos < initial_position]
    if not pairs:
        return MessagePlan([], [])
    ints, msgs = zip(*pairs)
    return MessagePlan(list(ints), list(msgs))


class ArmaWatcher:
    def __init__(
        self,
        monitor_index: int | None = None,
        queue_interval: int = 20,
        detect_interval: int = 5,
        model: str = MODEL,
        discord_url: str | None = None,
        discord_user_id: str | None = None,
        log_callback: Callable[[str], None] | None = None,
        inference_mode: str = "local",
        proxy_url: str | None = None,
        license_key: str | None = None,
    ):
        self.monitor_index = monitor_index
        self.queue_interval = queue_interval
        self.detect_interval = detect_interval
        self.model = model
        self.discord_url = discord_url
        self.discord_user_id = discord_user_id
        self.log_callback = log_callback
        self.inference_mode = inference_mode
        self.proxy_url = proxy_url
        self.license_key = license_key
        self.server_name: str | None = None
        self.history: list[QueueEntry] = []
        self.message_plan: MessagePlan | None = None
        self._notified_thresholds: set[int] = set()
        self._inference = None
        self._arma_attempts = 0
        self._front_of_queue_at: datetime | None = None
        self._stop_reason: str | None = None
        self._stop = threading.Event()
        self.state = (
            WatcherState.SEARCHING_QUEUE
            if monitor_index is not None
            else WatcherState.SEARCHING_ARMA
        )

    def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        if self.discord_url:
            ok = _notify_discord(self.discord_url, "Watching for queue...")
            if ok:
                self._log("Discord webhook OK.")
            else:
                self._log("Discord webhook FAILED — check URL in config.")
        if self.inference_mode == "cloud":
            if not self.proxy_url or not self.license_key:
                self._log("Cloud mode needs a proxy URL and license key — set them in Settings.")
                return
            self._log("Cloud inference mode — using subscription service.")

        try:
            try:
                if self.inference_mode != "cloud":
                    self._infer_call(lambda: ensure_model(self.model, self._log))
                while self.state != WatcherState.IN_GAME and not self._stop.is_set():
                    if self._front_of_queue_timed_out():
                        self._end_front_of_queue_timeout()
                        break
                    if self.state == WatcherState.SEARCHING_ARMA:
                        self._step_searching_arma()
                    elif self.state == WatcherState.SEARCHING_QUEUE:
                        self._step_searching_queue()
                    elif self.state == WatcherState.IN_QUEUE:
                        self._step_in_queue()
            except _WatcherStopped:
                pass  # stop() during a retry backoff — fall through to shutdown
            self._make_inference().unload()  # free VRAM (no-op in cloud mode)
            if self.state == WatcherState.IN_GAME:
                self._log("You're in the game! LLM unloaded from VRAM.")
                if self.discord_url:
                    _notify_discord(self.discord_url, f"{self._mention}You're in! Get on the server.")
            elif self._stop_reason:
                self._log(self._stop_reason)
            else:
                self._log("Stopped.")
        except CloudAuthError as e:
            self._log(str(e))
            self._log("Stopped.")
        except KeyboardInterrupt:
            print("\nStopping — unloading model from VRAM...")
            try:
                self._make_inference().unload()
                print("Model unloaded.")
            except Exception as e:
                print(f"Could not unload model: {e}")
            print("Stopped.")

    # ------------------------------------------------------------------
    # State steps
    # ------------------------------------------------------------------

    def _step_searching_arma(self) -> None:
        self._arma_attempts += 1
        self._log(
            f"Scanning monitors for Arma Reforger "
            f"(attempt {self._arma_attempts}/{_MAX_ARMA_ATTEMPTS})..."
        )
        inference = self._make_inference()
        for i in range(1, len(list_monitors())):
            if self._infer_call(lambda i=i: inference.is_arma(capture_to_bytes(i))):
                self.monitor_index = i
                self.state = WatcherState.SEARCHING_QUEUE
                self._log(f"Arma Reforger detected on monitor {i}. Waiting for queue...")
                return
        if self._arma_attempts >= _MAX_ARMA_ATTEMPTS:
            self._stop_reason = (
                f"Couldn't find Arma Reforger after {_MAX_ARMA_ATTEMPTS} attempts. "
                "Make sure the game is running and on screen, then start the watcher again."
            )
            self.stop()
            return
        self._stop.wait(self.detect_interval)

    def _step_searching_queue(self) -> None:
        screen = self._get_screen_state()
        if screen.in_queue:
            self.server_name = screen.server_name or self.server_name
            self.state = WatcherState.IN_QUEUE
            self._record(screen.position)
            self.message_plan = _default_message_plan(screen.position)
            if self.discord_url:
                server = self.server_name or "unknown server"
                eta = self._predicted_minutes()
                eta_str = f" | ETA: ~{eta:.0f}min" if eta is not None else ""
                _notify_discord(
                    self.discord_url,
                    f"{self._mention}You're in the queue at position {screen.position} on {server}.{eta_str}",
                )
            self._log_queue(screen.position)
        elif screen.in_game:
            self.state = WatcherState.IN_GAME
        else:
            self._log("Waiting for queue...")
            self._stop.wait(self.detect_interval)

    def _step_in_queue(self) -> None:
        if self._stop.wait(self.queue_interval):
            return
        screen = self._get_screen_state()
        if screen.in_game:
            self.state = WatcherState.IN_GAME
        elif screen.in_queue:
            self.server_name = screen.server_name or self.server_name
            self._record(screen.position)
            self._log_queue(screen.position)
        else:
            self._log("Queue not visible. Waiting...")
            self.state = WatcherState.SEARCHING_QUEUE

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_inference(self):
        """Build (and cache) the inference backend for the configured mode.

        Caching keeps the cloud backend's session token alive across polls
        instead of re-exchanging the license key on every call.
        """
        if self._inference is None:
            self._inference = make_inference(
                {
                    "inference_mode": self.inference_mode,
                    "proxy_url": self.proxy_url,
                    "license_key": self.license_key,
                    "model": self.model,
                },
                model=self.model,
            )
        return self._inference

    def _get_screen_state(self) -> ScreenState:
        return self._infer_call(
            lambda: self._make_inference().get_screen_state(capture_to_bytes(self.monitor_index))
        )

    def _infer_call(self, fn: Callable[[], _T]) -> _T:
        """Run an inference call, retrying transient backend failures.

        ConnectionError (Ollama down / proxy unreachable) and rate limits are
        retried; CloudAuthError is *not* caught here — it propagates to run()
        so the watcher stops with a clear message.
        """
        _RETRY = 15
        _RATE_LIMIT_BACKOFF = 60
        while True:
            try:
                return fn()
            except ConnectionError:
                self._log(
                    f"Inference backend unavailable (Ollama stopped or proxy unreachable). "
                    f"Retrying in {_RETRY}s..."
                )
                self._backoff(_RETRY)
            except ollama.ResponseError as e:
                self._log(f"Ollama error ({e.status_code}): {e.error}. Retrying in {_RETRY}s...")
                self._backoff(_RETRY)
            except CloudRateLimitError:
                self._log(f"Rate limited by subscription service. Backing off {_RATE_LIMIT_BACKOFF}s...")
                self._backoff(_RATE_LIMIT_BACKOFF)

    def _backoff(self, seconds: float) -> None:
        """Sleep between retries, but bail out the instant stop() is called.

        A plain time.sleep() blocks run() from returning until the full backoff
        elapses — most painfully the 60s rate-limit backoff, which made Stop
        feel hung. Waiting on the stop event makes Stop take effect immediately.
        """
        if self._stop.wait(seconds):
            raise _WatcherStopped

    def _record(self, position: int) -> None:
        now = datetime.now()
        self.history.append(QueueEntry(now, position))
        # Start the front-of-queue clock the first time we reach the front.
        if position <= 1 and self._front_of_queue_at is None:
            self._front_of_queue_at = now

    def _front_of_queue_timed_out(self) -> bool:
        if self._front_of_queue_at is None:
            return False
        elapsed = (datetime.now() - self._front_of_queue_at).total_seconds()
        return elapsed >= _FRONT_OF_QUEUE_TIMEOUT_S

    def _end_front_of_queue_timeout(self) -> None:
        self._stop_reason = (
            "You've been at the front of the queue for over 15 minutes — "
            "you're almost certainly in the game now. Stopping the watcher."
        )
        if self.discord_url:
            _notify_discord(
                self.discord_url,
                f"{self._mention}You're likely in the game now — the watcher is stopping.",
            )
        self.stop()

    def _avg_rate(self) -> float | None:
        """Positions moved per minute, calculated from first and last history entries."""
        if len(self.history) < 2:
            return None
        elapsed = (self.history[-1].timestamp - self.history[0].timestamp).total_seconds() / 60
        if elapsed <= 0:
            return None
        moved = self.history[0].position - self.history[-1].position
        return moved / elapsed

    def _predicted_minutes(self) -> float | None:
        rate = self._avg_rate()
        if rate is None or rate <= 0:
            return None
        return self.history[-1].position / rate

    @property
    def _mention(self) -> str:
        return f"<@{self.discord_user_id}> " if self.discord_user_id else ""

    def _log(self, msg: str) -> None:
        formatted = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        print(formatted)
        if self.log_callback:
            self.log_callback(formatted)

    def _log_queue(self, position: int) -> None:
        rate = self._avg_rate()
        eta = self._predicted_minutes()
        server = self.server_name or "unknown server"
        rate_str = f"{rate:.1f}/min" if rate is not None else "--"
        eta_str = f"~{eta:.0f}min" if eta is not None else "--"
        self._log(f"Position: {position} | {server} | Rate: {rate_str} | ETA: {eta_str}")
        if not self.discord_url or self.message_plan is None:
            return
        for threshold, message in zip(self.message_plan.message_ints, self.message_plan.messages):
            if position <= threshold and threshold not in self._notified_thresholds:
                self._notified_thresholds.add(threshold)
                detail = f" | Position: {position} | Server: {server} | ETA: {eta_str}"
                _notify_discord(self.discord_url, self._mention + message + detail)
