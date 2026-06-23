import ctypes
import json
import os
import queue
import threading
import tkinter as tk
import tkinter.font as tkfont
import urllib.error
import urllib.request
import webbrowser
from tkinter import ttk

from arma_watcher import config as cfg_mod
from arma_watcher.watcher import ArmaWatcher, WatcherState

# ── Arma-inspired gray & gold palette ───────────────────────────────────────
BG       = "#111111"
SURFACE  = "#1c1c1c"
SURF2    = "#262626"
GOLD     = "#c8a84b"
GOLD_DIM = "#7a6530"
TEXT     = "#c8c8c8"
TEXT_DIM = "#606060"
BORDER   = "#2c2c2c"

# ── CRT phosphor log palette ─────────────────────────────────────────────────
LOG_BG   = "#040904"
LOG_FG   = "#33ff33"
LOG_TS   = "#1a7a1a"
LOG_ERR  = "#ff3333"
LOG_WARN = "#cc8800"
LOG_POS  = "#66ff66"
LOG_OK   = "#88ff88"

_MODELS = ["qwen3.5:0.8b", "qwen3.5:2b", "qwen3.5:4b", "qwen3.5:9b"]
_MODE_LOCAL = "Local (own VRAM)"
_MODE_CLOUD = "Cloud (subscription)"
_MODES = [_MODE_LOCAL, _MODE_CLOUD]
_FONT_PATH = os.path.join(os.path.dirname(__file__), "assets", "kent_handwriting.ttf")


def _read_ttf_family(path: str) -> str | None:
    """Parse the name table of a TTF/OTF file and return the family name."""
    try:
        with open(path, "rb") as f:
            f.seek(4)
            num_tables = int.from_bytes(f.read(2), "big")
            f.seek(12)
            tables: dict[str, tuple[int, int]] = {}
            for _ in range(num_tables):
                tag = f.read(4).decode("ascii", errors="replace")
                f.read(4)  # checksum
                off = int.from_bytes(f.read(4), "big")
                lng = int.from_bytes(f.read(4), "big")
                tables[tag] = (off, lng)

            if "name" not in tables:
                return None
            f.seek(tables["name"][0])
            nd = f.read(tables["name"][1])

        count = int.from_bytes(nd[2:4], "big")
        str_off = int.from_bytes(nd[4:6], "big")
        best: str | None = None
        for i in range(count):
            rec = nd[6 + i * 12: 6 + i * 12 + 12]
            pid  = int.from_bytes(rec[0:2], "big")
            nid  = int.from_bytes(rec[6:8], "big")
            slen = int.from_bytes(rec[8:10], "big")
            soff = int.from_bytes(rec[10:12], "big")
            if nid == 1:
                raw = nd[str_off + soff: str_off + soff + slen]
                name = raw.decode("utf-16-be" if pid == 3 else "latin-1", errors="ignore").strip()
                if name:
                    best = name
                    if pid == 3:  # Windows platform — most reliable
                        break
        return best
    except Exception:
        return None

_STATE_DISPLAY = {
    WatcherState.SEARCHING_ARMA:  ("Scanning for Arma Reforger", GOLD),
    WatcherState.SEARCHING_QUEUE: ("Waiting for queue",          GOLD),
    WatcherState.IN_QUEUE:        ("In queue",                   GOLD),
    WatcherState.IN_GAME:         ("In game!",                   LOG_OK),
}


class WatcherGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Arma Watcher")
        self.root.resizable(False, True)

        self._watcher: ArmaWatcher | None = None
        self._thread: threading.Thread | None = None
        self._log_q: queue.Queue[str] = queue.Queue()

        self._hw_font = self._load_handwriting_font()
        self._apply_theme()
        self._build_ui()
        self._load_settings()
        self._poll()

    # ── Font loading ────────────────────────────────────────────────────────

    def _load_handwriting_font(self) -> str:
        try:
            family = _read_ttf_family(_FONT_PATH)
            if family:
                ctypes.windll.gdi32.AddFontResourceW(_FONT_PATH)
                ctypes.windll.user32.SendMessageW(0xFFFF, 0x001D, 0, 0)
                return family
        except Exception:
            pass
        return "Segoe Script"

    # ── Theme ───────────────────────────────────────────────────────────────

    def _apply_theme(self) -> None:
        self.root.configure(bg=BG)
        s = ttk.Style(self.root)
        s.theme_use("clam")

        s.configure(".", background=BG, foreground=TEXT,
                    fieldbackground=SURF2, bordercolor=BORDER,
                    darkcolor=BORDER, lightcolor=BORDER,
                    troughcolor=SURFACE, selectbackground=GOLD,
                    selectforeground="#111111",
                    insertcolor=TEXT, font=("Segoe UI", 9))

        s.configure("TFrame", background=BG)
        s.configure("TLabel", background=BG, foreground=TEXT)

        s.configure("TEntry", fieldbackground=SURF2, foreground=TEXT,
                    insertcolor=TEXT, bordercolor=BORDER, padding=5)
        s.map("TEntry", bordercolor=[("focus", GOLD)])

        s.configure("TCombobox", fieldbackground=SURF2, foreground=TEXT,
                    selectbackground=GOLD, bordercolor=BORDER, arrowcolor=TEXT_DIM)
        s.map("TCombobox",
              fieldbackground=[("readonly", SURF2)],
              bordercolor=[("focus", GOLD)])

        s.configure("TSpinbox", fieldbackground=SURF2, foreground=TEXT,
                    arrowcolor=TEXT_DIM, bordercolor=BORDER, padding=4)
        s.map("TSpinbox", bordercolor=[("focus", GOLD)])

        s.configure("TScrollbar", background=SURF2, troughcolor=SURFACE,
                    bordercolor=BORDER, arrowcolor=TEXT_DIM, relief="flat")
        s.map("TScrollbar", background=[("active", "#383838")])

        s.configure("TButton", background=SURF2, foreground=TEXT,
                    bordercolor=BORDER, relief="flat", padding=(12, 7))
        s.map("TButton",
              background=[("active", "#303030"), ("disabled", SURFACE)],
              foreground=[("disabled", TEXT_DIM)])

        s.configure("Gold.TButton", background=SURF2, foreground=GOLD,
                    bordercolor=GOLD_DIM, relief="groove", padding=(12, 7))
        s.map("Gold.TButton",
              background=[("active", "#1e1a0e"), ("disabled", SURFACE)],
              foreground=[("disabled", "#4a3a20")])

        s.configure("Danger.TButton", background=SURF2, foreground="#cc4444",
                    bordercolor="#4a2020", relief="groove", padding=(12, 7))
        s.map("Danger.TButton",
              background=[("active", "#1e1010"), ("disabled", SURFACE)],
              foreground=[("disabled", "#663333")])

        self.root.option_add("*TCombobox*Listbox.background", SURF2)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", GOLD)
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#111111")

    # ── UI construction ─────────────────────────────────────────────────────

    def _card(self, parent, accent_stripe: bool = False, expand: bool = False) -> tk.Frame:
        """Return a card frame. If accent_stripe=True, add a gold left border."""
        outer = tk.Frame(parent, bg=BORDER)
        outer.pack(fill="both" if expand else "x", expand=expand, pady=(0, 8))
        if accent_stripe:
            tk.Frame(outer, bg=GOLD, width=3).pack(side="left", fill="y")
        inner = tk.Frame(outer, bg=SURFACE)
        inner.pack(side="left", fill="both", expand=True, padx=(0 if accent_stripe else 1), pady=1)
        return inner

    def _section_header(self, parent, text: str) -> None:
        tk.Label(parent, text=text, bg=SURFACE, fg=GOLD,
                 font=(self._hw_font, 13)).pack(anchor="w")
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", pady=(3, 10))

    def _build_ui(self) -> None:
        hw = self._hw_font
        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill="both", expand=True, padx=14, pady=12)

        # ── App header ───────────────────────────────────────────────────────
        hdr = tk.Frame(outer, bg=BG)
        hdr.pack(fill="x", pady=(0, 10))
        tk.Label(hdr, text="Arma Watcher", bg=BG, fg=GOLD,
                 font=(hw, 22)).pack(side="left")
        tk.Label(hdr, text=" queue monitor", bg=BG, fg=TEXT_DIM,
                 font=("Segoe UI", 9)).pack(side="left", pady=(12, 0))

        # ── Status card (gold left stripe) ──────────────────────────────────
        status_body = self._card(outer, accent_stripe=True)
        si = tk.Frame(status_body, bg=SURFACE)
        si.pack(fill="x", padx=14, pady=12)

        self._section_header(si, "Status")

        row = tk.Frame(si, bg=SURFACE)
        row.pack(anchor="w")
        self._dot_lbl = tk.Label(row, text="●", bg=SURFACE, fg=TEXT_DIM,
                                  font=("Segoe UI", 18))
        self._dot_lbl.pack(side="left")
        self._state_lbl = tk.Label(row, text="  Stopped", bg=SURFACE, fg=TEXT,
                                    font=("Segoe UI", 14, "bold"))
        self._state_lbl.pack(side="left")

        self._detail_lbl = tk.Label(si, text="", bg=SURFACE, fg=TEXT_DIM,
                                     font=("Segoe UI", 9))
        self._detail_lbl.pack(anchor="w", pady=(2, 0))

        tk.Frame(si, bg=BORDER, height=1).pack(fill="x", pady=(10, 10))

        btn_row = tk.Frame(si, bg=SURFACE)
        btn_row.pack(anchor="w")
        self._start_btn = ttk.Button(btn_row, text="Start Watching", width=14,
                                      style="Gold.TButton", command=self._start)
        self._start_btn.pack(side="left", padx=(0, 8))
        self._stop_btn = ttk.Button(btn_row, text="Stop", width=8,
                                     style="Danger.TButton", command=self._stop,
                                     state="disabled")
        self._stop_btn.pack(side="left")

        # ── Settings card ────────────────────────────────────────────────────
        settings_body = self._card(outer)
        sb = tk.Frame(settings_body, bg=SURFACE)
        sb.pack(fill="x", padx=14, pady=12)

        self._section_header(sb, "Settings")

        self._sv: dict[str, tk.StringVar] = {}
        self._field_widgets: dict[str, tuple[tk.Widget, tk.Widget]] = {}
        grid = tk.Frame(sb, bg=SURFACE)
        grid.pack(fill="x")

        fields = [
            ("inference_mode",     "Inference",          "combo",   {"values": _MODES, "state": "readonly", "width": 20}),
            ("discord_webhook",    "Discord Webhook",    "entry",   {}),
            ("discord_user_id",    "Discord User ID",    "entry",   {}),
            ("model",              "Model",              "combo",   {"values": _MODELS, "state": "readonly", "width": 18}),
            ("proxy_url",          "Service URL",        "entry",   {}),
            ("subscription_email", "Subscription Email", "entry",   {}),
            ("monitor",            "Monitor",            "combo",   {"values": ["Auto", "1", "2", "3", "4", "5"], "width": 8}),
            ("interval",           "Queue Interval (s)", "spinbox", {"from_": 5, "to": 300, "width": 8}),
            ("detect_interval",    "Detect Interval (s)","spinbox", {"from_": 1, "to": 60,  "width": 8}),
        ]
        for row_i, (key, label, kind, kw) in enumerate(fields):
            lbl = tk.Label(grid, text=label, bg=SURFACE, fg=TEXT_DIM,
                           font=("Segoe UI", 9))
            lbl.grid(row=row_i, column=0, sticky="w", pady=3, padx=(0, 12))
            sv = tk.StringVar()
            self._sv[key] = sv
            if kind == "entry":
                w: tk.Widget = ttk.Entry(grid, textvariable=sv, width=36, **kw)
            elif kind == "combo":
                w = ttk.Combobox(grid, textvariable=sv, **kw)
            else:
                w = ttk.Spinbox(grid, textvariable=sv, **kw)
            w.grid(row=row_i, column=1, sticky="w", pady=3)
            self._field_widgets[key] = (lbl, w)

        self._sv["inference_mode"].trace_add("write", self._on_mode_change)

        save_row = tk.Frame(sb, bg=SURFACE)
        save_row.pack(fill="x", pady=(10, 0))
        ttk.Button(save_row, text="Save Settings",
                   command=self._save_settings).pack(side="right")
        self._manage_btn = ttk.Button(save_row, text="Manage Subscription",
                                      command=self._open_portal)
        self._manage_btn.pack(side="left")

        # ── Log card ─────────────────────────────────────────────────────────
        log_body = self._card(outer, expand=True)
        lb = tk.Frame(log_body, bg=SURFACE)
        lb.pack(fill="both", expand=True, padx=14, pady=12)

        self._section_header(lb, "Log")

        crt_border = tk.Frame(lb, bg="#1a3a1a", highlightthickness=0)
        crt_border.pack(fill="both", expand=True)

        self._log_txt = tk.Text(
            crt_border, height=10, state="disabled",
            font=("Consolas", 9), wrap="word",
            bg=LOG_BG, fg=LOG_FG,
            insertbackground=LOG_FG,
            selectbackground="#1a5a1a",
            selectforeground=LOG_OK,
            borderwidth=0, highlightthickness=0,
            padx=8, pady=6,
        )
        scrollbar = ttk.Scrollbar(crt_border, command=self._log_txt.yview)
        self._log_txt.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._log_txt.pack(side="left", fill="both", expand=True)

        self._log_txt.tag_configure("ts",      foreground=LOG_TS)
        self._log_txt.tag_configure("error",   foreground=LOG_ERR)
        self._log_txt.tag_configure("warn",    foreground=LOG_WARN)
        self._log_txt.tag_configure("pos",     foreground=LOG_POS)
        self._log_txt.tag_configure("success", foreground=LOG_OK)
        self._log_txt.tag_configure("dim",     foreground="#0d6e0d")

        # Patch log_body's outer Frame so it also fills vertically
        log_body.master.pack_configure(fill="both", expand=True)

    # ── Settings ─────────────────────────────────────────────────────────────

    def _load_settings(self) -> None:
        cfg = cfg_mod.load()
        self._sv["inference_mode"].set(
            _MODE_CLOUD if cfg.get("inference_mode") == "cloud" else _MODE_LOCAL
        )
        self._sv["discord_webhook"].set(cfg.get("discord_webhook") or "")
        self._sv["discord_user_id"].set(cfg.get("discord_user_id") or "")
        self._sv["model"].set(cfg.get("model", "qwen3.5:9b"))
        self._sv["proxy_url"].set(cfg.get("proxy_url") or "")
        self._sv["subscription_email"].set(cfg.get("subscription_email") or "")
        m = cfg.get("monitor")
        self._sv["monitor"].set(str(m) if m is not None else "Auto")
        self._sv["interval"].set(str(cfg.get("interval", 20)))
        self._sv["detect_interval"].set(str(cfg.get("detect_interval", 5)))
        self._on_mode_change()

    def _save_settings(self) -> None:
        cfg = cfg_mod.load()
        cfg["inference_mode"] = "cloud" if self._sv["inference_mode"].get() == _MODE_CLOUD else "local"
        cfg["discord_webhook"] = self._sv["discord_webhook"].get().strip() or None
        cfg["discord_user_id"] = self._sv["discord_user_id"].get().strip() or None
        cfg["model"] = self._sv["model"].get()
        cfg["proxy_url"] = self._sv["proxy_url"].get().strip() or None
        cfg["subscription_email"] = self._sv["subscription_email"].get().strip() or None
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

    # ── Inference mode (local vs cloud) ───────────────────────────────────────

    def _on_mode_change(self, *_args) -> None:
        """Show local-only fields in Local mode and cloud-only fields in Cloud."""
        cloud = self._sv["inference_mode"].get() == _MODE_CLOUD
        for key in ("model",):
            self._set_field_visible(key, not cloud)
        for key in ("proxy_url", "subscription_email"):
            self._set_field_visible(key, cloud)
        if cloud:
            self._manage_btn.pack(side="left")
        else:
            self._manage_btn.pack_forget()

    def _set_field_visible(self, key: str, visible: bool) -> None:
        lbl, w = self._field_widgets[key]
        if visible:
            lbl.grid()
            w.grid()
        else:
            lbl.grid_remove()
            w.grid_remove()

    def _open_portal(self) -> None:
        proxy = self._sv["proxy_url"].get().strip().rstrip("/")
        email = self._sv["subscription_email"].get().strip()
        if not proxy or not email:
            self._append_log("Enter your Service URL and Subscription Email first.")
            return
        req = urllib.request.Request(
            f"{proxy}/portal",
            data=json.dumps({"email": email}).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "ArmaWatcher/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                url = json.loads(resp.read())["url"]
        except urllib.error.HTTPError as e:
            if e.code in (402, 403):
                self._append_log("No active subscription found for that email.")
            else:
                self._append_log(f"Could not open billing portal (error {e.code}).")
            return
        except Exception as e:
            self._append_log(f"Could not reach billing service: {e}")
            return
        webbrowser.open(url)
        self._append_log("Opened subscription management in your browser.")

    # ── Watcher control ──────────────────────────────────────────────────────

    def _start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._save_settings()
        cfg = cfg_mod.load()
        if cfg.get("inference_mode") == "cloud" and (
            not cfg.get("proxy_url") or not cfg.get("subscription_email")
        ):
            self._append_log("Cloud mode needs a Service URL and Subscription Email.")
            return
        self._watcher = ArmaWatcher(
            monitor_index=cfg.get("monitor"),
            queue_interval=cfg.get("interval", 20),
            detect_interval=cfg.get("detect_interval", 5),
            discord_url=cfg.get("discord_webhook"),
            discord_user_id=cfg.get("discord_user_id"),
            model=cfg.get("model", "qwen3.5:9b"),
            log_callback=self._log_q.put,
            inference_mode=cfg.get("inference_mode", "local"),
            proxy_url=cfg.get("proxy_url"),
            subscription_email=cfg.get("subscription_email"),
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

    # ── Poll loop ────────────────────────────────────────────────────────────

    def _poll(self) -> None:
        try:
            while True:
                msg = self._log_q.get_nowait()
                if msg == "\x00STOPPED":
                    self._start_btn.config(state="normal")
                    self._stop_btn.config(state="disabled")
                    self._dot_lbl.config(fg=TEXT_DIM)
                    self._state_lbl.config(text="  Stopped", fg=TEXT)
                    self._detail_lbl.config(text="")
                else:
                    self._append_log(msg)
        except queue.Empty:
            pass

        if self._watcher and self._thread and self._thread.is_alive():
            state = self._watcher.state
            text, color = _STATE_DISPLAY.get(state, ("Running", TEXT_DIM))

            if state == WatcherState.IN_QUEUE and self._watcher.history:
                pos = self._watcher.history[-1].position
                eta = self._watcher._predicted_minutes()
                server = self._watcher.server_name or ""
                detail = f"Position: #{pos}"
                if server:
                    detail += f"  ·  {server}"
                if eta is not None:
                    detail += f"  ·  ETA ~{eta:.0f}min"
                self._dot_lbl.config(fg=color)
                self._state_lbl.config(text=f"  {text}", fg=TEXT)
                self._detail_lbl.config(text=detail)
            else:
                self._dot_lbl.config(fg=color)
                self._state_lbl.config(text=f"  {text}", fg=TEXT)
                self._detail_lbl.config(text="")

        self.root.after(300, self._poll)

    def _append_log(self, msg: str) -> None:
        self._log_txt.config(state="normal")
        lower = msg.lower()

        if msg.startswith("[") and "]" in msg[:12]:
            end = msg.index("]") + 1
            ts, rest = msg[:end], msg[end:]
            self._log_txt.insert("end", ts, "ts")

            if "error" in lower or "failed" in lower:
                tag = "error"
            elif ("ollama" in lower and "not" in lower) or "discord" in lower:
                tag = "warn"
            elif "position:" in lower or "in queue" in lower:
                tag = "pos"
            elif "in the game" in lower or "you're in" in lower or "in game" in lower:
                tag = "success"
            else:
                tag = ""
            self._log_txt.insert("end", rest + "\n", tag)
        else:
            self._log_txt.insert("end", msg + "\n")

        self._log_txt.see("end")
        self._log_txt.config(state="disabled")


def main() -> None:
    # Tell Windows this is its own app, not python.exe — fixes taskbar icon
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ArmaWatcher.App.1")

    root = tk.Tk()
    root.minsize(500, 580)

    _icon = os.path.join(os.path.dirname(__file__), "assets", "icon.ico")
    if os.path.isfile(_icon):
        root.iconbitmap(_icon)

    WatcherGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
