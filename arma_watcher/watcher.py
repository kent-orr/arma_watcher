import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from arma_watcher.inference import Inference, MODEL, ScreenState
from arma_watcher.screenshot import capture_to_bytes, list_monitors


class WatcherState(Enum):
    SEARCHING_ARMA = "searching_arma"
    SEARCHING_QUEUE = "searching_queue"
    IN_QUEUE = "in_queue"
    IN_GAME = "in_game"


@dataclass
class QueueEntry:
    timestamp: datetime
    position: int


class ArmaWatcher:
    def __init__(
        self,
        monitor_index: int | None = None,
        queue_interval: int = 20,
        detect_interval: int = 5,
        model: str = MODEL,
    ):
        self.monitor_index = monitor_index
        self.queue_interval = queue_interval
        self.detect_interval = detect_interval
        self.model = model
        self.server_name: str | None = None
        self.history: list[QueueEntry] = []
        self.state = (
            WatcherState.SEARCHING_QUEUE
            if monitor_index is not None
            else WatcherState.SEARCHING_ARMA
        )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        try:
            while self.state != WatcherState.IN_GAME:
                if self.state == WatcherState.SEARCHING_ARMA:
                    self._step_searching_arma()
                elif self.state == WatcherState.SEARCHING_QUEUE:
                    self._step_searching_queue()
                elif self.state == WatcherState.IN_QUEUE:
                    self._step_in_queue()
            Inference(model=self.model).unload()  # free VRAM — we're in, don't need the LLM anymore
            self._log("You're in the game! LLM unloaded from VRAM.")
        except KeyboardInterrupt:
            print("\nStopped.")

    # ------------------------------------------------------------------
    # State steps
    # ------------------------------------------------------------------

    def _step_searching_arma(self) -> None:
        self._log("Scanning monitors for Arma Reforger...")
        inference = Inference(model=self.model)
        for i in range(1, len(list_monitors())):
            if inference.is_arma(capture_to_bytes(i)):
                self.monitor_index = i
                self.state = WatcherState.SEARCHING_QUEUE
                self._log(f"Arma Reforger detected on monitor {i}. Waiting for queue...")
                return
        time.sleep(self.detect_interval)

    def _step_searching_queue(self) -> None:
        screen = self._get_screen_state()
        if screen.in_queue:
            self.server_name = screen.server_name or self.server_name
            self.state = WatcherState.IN_QUEUE
            self._record(screen.position)
            self._log_queue(screen.position)
        elif screen.in_game:
            self.state = WatcherState.IN_GAME
        else:
            self._log("Waiting for queue...")
            time.sleep(self.detect_interval)

    def _step_in_queue(self) -> None:
        time.sleep(self.queue_interval)
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

    def _get_screen_state(self) -> ScreenState:
        return Inference(model=self.model).get_screen_state(capture_to_bytes(self.monitor_index))

    def _record(self, position: int) -> None:
        self.history.append(QueueEntry(datetime.now(), position))

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

    def _log(self, msg: str) -> None:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def _log_queue(self, position: int) -> None:
        rate = self._avg_rate()
        eta = self._predicted_minutes()
        server = self.server_name or "unknown server"
        rate_str = f"{rate:.1f}/min" if rate is not None else "--"
        eta_str = f"~{eta:.0f}min" if eta is not None else "--"
        self._log(f"Position: {position} | {server} | Rate: {rate_str} | ETA: {eta_str}")
