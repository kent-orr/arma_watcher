import queue
import threading
import tkinter as tk
from tkinter import scrolledtext, ttk

from arma_watcher import config as cfg_mod
from arma_watcher.watcher import ArmaWatcher, WatcherState

_MODELS = ["qwen3.5:0.8b", "qwen3.5:2b", "qwen3.5:4b", "qwen3.5:9b"]

_STATE_DISPLAY = {
    WatcherState.SEARCHING_ARMA:  ("Scanning for Arma Reforger...", "#e6a817"),
    WatcherState.SEARCHING_QUEUE: ("Waiting for queue...",          "#e6a817"),
    WatcherState.IN_QUEUE:        ("In queue",                      "#3a9bdc"),
    WatcherState.IN_GAME:         ("In game!",                      "#4caf50"),
}


class WatcherGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Arma Watcher")
        self.root.resizable(False, True)

        self._watcher: ArmaWatcher | None = None
        self._thread: threading.Thread | None = None
        self._log_q: queue.Queue[str] = queue.Queue()

        self._build_ui()
        self._load_settings()
        self._poll()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 6}

        # Status
        sf = ttk.LabelFrame(self.root, text="Status", padding=8)
        sf.pack(fill="x", **pad)

        self._state_lbl = ttk.Label(sf, text="● Stopped", font=("Segoe UI", 11, "bold"), foreground="gray")
        self._state_lbl.pack(anchor="w")
        self._detail_lbl = ttk.Label(sf, text="", foreground="gray")
        self._detail_lbl.pack(anchor="w")

        btn_row = ttk.Frame(sf)
        btn_row.pack(anchor="w", pady=(8, 0))
        self._start_btn = ttk.Button(btn_row, text="Start", width=10, command=self._start)
        self._start_btn.pack(side="left", padx=(0, 6))
        self._stop_btn = ttk.Button(btn_row, text="Stop", width=10, command=self._stop, state="disabled")
        self._stop_btn.pack(side="left")

        # Settings
        settings_f = ttk.LabelFrame(self.root, text="Settings", padding=8)
        settings_f.pack(fill="x", **pad)

        self._sv: dict[str, tk.StringVar] = {}
        fields = [
            ("discord_webhook",  "Discord Webhook",      "entry",   {}),
            ("discord_user_id",  "Discord User ID",      "entry",   {}),
            ("model",            "Model",                "combo",   {"values": _MODELS, "state": "readonly", "width": 18}),
            ("monitor",          "Monitor",              "combo",   {"values": ["Auto", "1", "2", "3", "4", "5"], "width": 8}),
            ("interval",         "Queue Interval (s)",   "spinbox", {"from_": 5, "to": 300, "width": 6}),
            ("detect_interval",  "Detect Interval (s)",  "spinbox", {"from_": 1, "to": 60,  "width": 6}),
        ]
        for row, (key, label, kind, kw) in enumerate(fields):
            ttk.Label(settings_f, text=label + ":").grid(row=row, column=0, sticky="w", pady=2)
            sv = tk.StringVar()
            self._sv[key] = sv
            if kind == "entry":
                w: tk.Widget = ttk.Entry(settings_f, textvariable=sv, width=38, **kw)
            elif kind == "combo":
                w = ttk.Combobox(settings_f, textvariable=sv, **kw)
            else:
                w = ttk.Spinbox(settings_f, textvariable=sv, **kw)
            w.grid(row=row, column=1, sticky="w", padx=(8, 0), pady=2)

        ttk.Button(settings_f, text="Save Settings", command=self._save_settings).grid(
            row=len(fields), column=0, columnspan=2, sticky="w", pady=(8, 2)
        )

        # Log
        log_f = ttk.LabelFrame(self.root, text="Log", padding=8)
        log_f.pack(fill="both", expand=True, **pad)

        self._log_txt = scrolledtext.ScrolledText(
            log_f, height=12, state="disabled", font=("Consolas", 9), wrap="word"
        )
        self._log_txt.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _load_settings(self) -> None:
        cfg = cfg_mod.load()
        self._sv["discord_webhook"].set(cfg.get("discord_webhook") or "")
        self._sv["discord_user_id"].set(cfg.get("discord_user_id") or "")
        self._sv["model"].set(cfg.get("model", "qwen3.5:9b"))
        m = cfg.get("monitor")
        self._sv["monitor"].set(str(m) if m is not None else "Auto")
        self._sv["interval"].set(str(cfg.get("interval", 20)))
        self._sv["detect_interval"].set(str(cfg.get("detect_interval", 5)))

    def _save_settings(self) -> None:
        cfg = cfg_mod.load()
        cfg["discord_webhook"] = self._sv["discord_webhook"].get().strip() or None
        cfg["discord_user_id"] = self._sv["discord_user_id"].get().strip() or None
        cfg["model"] = self._sv["model"].get()
        raw_monitor = self._sv["monitor"].get().strip()
        cfg["monitor"] = int(raw_monitor) if raw_monitor.isdigit() else None
        try:
            cfg["interval"] = int(self._sv["interval"].get())
        except ValueError:
            cfg["interval"] = 20
        try:
            cfg["detect_interval"] = int(self._sv["detect_interval"].get())
        except ValueError:
            cfg["detect_interval"] = 5
        cfg_mod.save(cfg)
        self._append_log("Settings saved.")

    # ------------------------------------------------------------------
    # Watcher control
    # ------------------------------------------------------------------

    def _start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._save_settings()
        cfg = cfg_mod.load()
        self._watcher = ArmaWatcher(
            monitor_index=cfg.get("monitor"),
            queue_interval=cfg.get("interval", 20),
            detect_interval=cfg.get("detect_interval", 5),
            discord_url=cfg.get("discord_webhook"),
            discord_user_id=cfg.get("discord_user_id"),
            model=cfg.get("model", "qwen3.5:9b"),
            log_callback=self._log_q.put,
        )
        self._thread = threading.Thread(target=self._run_watcher, daemon=True)
        self._thread.start()
        self._start_btn.config(state="disabled")
        self._stop_btn.config(state="normal")

    def _run_watcher(self) -> None:
        try:
            self._watcher.run()
        except Exception as e:
            self._log_q.put(f"[error] {e}")
        finally:
            self._log_q.put("\x00STOPPED")

    def _stop(self) -> None:
        if self._watcher:
            self._watcher.stop()

    # ------------------------------------------------------------------
    # Poll loop (runs on main thread via after())
    # ------------------------------------------------------------------

    def _poll(self) -> None:
        try:
            while True:
                msg = self._log_q.get_nowait()
                if msg == "\x00STOPPED":
                    self._start_btn.config(state="normal")
                    self._stop_btn.config(state="disabled")
                    self._state_lbl.config(text="● Stopped", foreground="gray")
                    self._detail_lbl.config(text="")
                else:
                    self._append_log(msg)
        except queue.Empty:
            pass

        if self._watcher and self._thread and self._thread.is_alive():
            state = self._watcher.state
            text, color = _STATE_DISPLAY.get(state, ("Running", "gray"))

            if state == WatcherState.IN_QUEUE and self._watcher.history:
                pos = self._watcher.history[-1].position
                eta = self._watcher._predicted_minutes()
                server = self._watcher.server_name or ""
                detail = f"#{pos}"
                if server:
                    detail += f"  •  {server}"
                eta_str = f"  •  ETA ~{eta:.0f}min" if eta is not None else ""
                self._state_lbl.config(text=f"● In queue: {detail}{eta_str}", foreground=color)
                self._detail_lbl.config(text="")
            else:
                self._state_lbl.config(text=f"● {text}", foreground=color)
                self._detail_lbl.config(text="")

        self.root.after(300, self._poll)

    def _append_log(self, msg: str) -> None:
        self._log_txt.config(state="normal")
        self._log_txt.insert("end", msg + "\n")
        self._log_txt.see("end")
        self._log_txt.config(state="disabled")


def main() -> None:
    root = tk.Tk()
    root.minsize(500, 560)
    WatcherGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
