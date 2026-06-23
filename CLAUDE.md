# CLAUDE.md — Arma Watcher (desktop client)

Cross-platform desktop app (Windows / Linux / macOS) that watches the **Arma
Reforger** server-queue screen, reads
the queue position + server name with a **vision model**, and fires **Discord
webhook** notifications with position and ETA so the user can alt-tab away and get
pinged before they're in.

This is the **client half** of a two-repo system. The **server half** lives in the
sibling repo [`../arma_watcher_server`](../arma_watcher_server) — a Flask proxy that
gates cloud inference behind a Stripe subscription. The two are bound by an HTTP
contract (see *Inference modes* below and the server's `PLAN.md`); change the
contract on one side and you must change it on the other.

## Purpose & monetization role

Inference can run two ways, chosen by `inference_mode` in config:

- **`local`** (default, free) — runs a vision model on the user's own GPU via
  [Ollama](https://ollama.com). Screenshots never leave the machine. No account.
- **`cloud`** (paid) — POSTs screenshots to `arma_watcher_server`, which holds the
  DigitalOcean inference key and only answers for an **active Stripe subscriber**.
  This is the monetized path: the user stores their *purchase email*, the proxy
  exchanges it for a short-lived opaque session token, inference is metered and
  rate-limited server-side.

The client is deliberately ignorant of Stripe/DO — it only knows a proxy URL, an
email, and the token dance. All payment/secrets live in the server.

## Layout

```
arma_watcher/            importable package
  cli.py                 headless entrypoint (`arma-watcher`); arg parsing + ArmaWatcher wiring
  gui.py                 Tkinter GUI (`arma-watcher-gui`); Arma-themed, CRT log panel
  __main__.py            `python -m arma_watcher` → cli.main()
  config.py              load/save ~/.arma_watcher/config.json; first-run setup wizard; env overrides
  watcher.py             ArmaWatcher state machine (the core loop) + Discord notifications
  inference.py           OllamaInference + CloudInference (same interface) + make_inference() factory
  screenshot.py          mss-based monitor capture → PNG bytes
  updater.py             self-update by pulling the GitHub repo zip (compares commit SHA)
launchers/               all run/install/update launchers, tucked out of the repo root:
  *.ps1 / *.bat / *.vbs    Windows launchers (run, install, update) + dev.ps1 (cloud-mode dev launcher)
  *.sh                     Linux/macOS launchers: install.sh (setup + .desktop), run.sh (GUI)
installer/               Inno Setup (.iss) one-click Windows installer + bootstrap.ps1
docs/                    GitHub Pages download page (index.html)
tests/                   pytest; do_serverless_probe.py is a DO cost/shape probe (not a unit test)
```

Every launcher lives in `launchers/` and `cd`s up one level to the repo root before
calling `uv`, so `uv` always sees `pyproject.toml`. The Windows installer copies them
to `{app}\launchers` (matching layout) and self-update refreshes the whole folder.

## Core design

- **State machine** (`watcher.py`, `WatcherState`): `SEARCHING_ARMA` → scans monitors
  for Arma; `SEARCHING_QUEUE` → watches for a queue screen; `IN_QUEUE` → polls position
  every `queue_interval`s; `IN_GAME` → terminal, unloads model + sends final ping.
- **Inference is pluggable**: `OllamaInference` and `CloudInference` expose the *same*
  three methods — `is_arma()`, `get_screen_state()`, `run()` — plus `unload()`.
  `make_inference(cfg)` picks one by `inference_mode`. Keep the interfaces identical;
  the watcher must not care which backend it holds. The backend is built once and
  cached (`_make_inference`) so the cloud session token survives across polls.
- **Structured output**: models are constrained to Pydantic schemas (`QueueInfo`,
  `ScreenState`, `_ArmaDetection`). Local Ollama enforces the JSON schema natively;
  cloud appends the schema to the prompt and `_coerce_json` trims stray prose before
  parsing. `_parse` has a regex fallback to salvage a bare integer position.
- **ETA**: `_avg_rate()` = positions moved / minutes elapsed across history;
  `_predicted_minutes()` = current position / rate. Notifications are milestone-gated
  (`_MILESTONES`) so Discord isn't spammed; milestones the queue starts below are skipped.
- **Resilience**: `_infer_call` retries `ConnectionError` (Ollama down / proxy
  unreachable) and `CloudRateLimitError` (429, ~60s backoff) indefinitely, but lets
  `CloudAuthError` (402/403, bad subscription) propagate so the watcher stops with a
  clear message.

## Inference modes & the server contract

`CloudInference` (in `inference.py`) is the client side of the contract documented in
`../arma_watcher_server/PLAN.md`. Key invariants — keep both repos in sync:

- `POST /token` `{email}` → `{token, expires_at}`; `402/403` → `CloudAuthError`.
- `POST /v1/chat/completions` with `Authorization: Bearer <token>`, OpenAI-style body
  (`messages` with a `data:image/png;base64,...` image_url, `max_tokens`, `temperature`).
  The server **ignores** the client's model/prompt and injects its own — the client
  still sends a prompt + schema, but must not depend on them being honored verbatim.
- Status codes the client depends on: `200` ok · `401/403` refresh token once then
  `CloudAuthError` · `402` `CloudAuthError` · `429` `CloudRateLimitError` (back off) ·
  `413` payload too large.

## Config

`~/.arma_watcher/config.json` (see `DEFAULTS` in `config.py`). Never written by tests.
Three env vars override config at load time **without persisting** — used by `dev.ps1`
to point the GUI at a local server: `ARMA_WATCHER_INFERENCE_MODE`,
`ARMA_WATCHER_PROXY_URL`, `ARMA_WATCHER_SUBSCRIPTION_EMAIL`. `config.save()` is careful
not to bake an active override into the file.

## Dev & testing

This project uses **test-driven development**. Prefer pure unit tests (no Ollama, no
display); they cover state init, ETA math, message planning, and JSON coercion.

```bash
uv sync                 # set up the venv
uv run pytest           # unit tests
uv run arma-watcher           # headless, saved config
uv run arma-watcher --setup   # re-run setup wizard
uv run arma-watcher-gui       # GUI
```

- Tests in `test_inference.py` marked as hitting "the real ollama stack" need Ollama
  running with a model loaded — keep those separable from pure unit tests.
- `tests/do_serverless_probe.py` is a manual cost/shape probe against DigitalOcean, not
  a unit test. `tests/queue_test.png` is the reference queue screenshot fixture.
- End-to-end against the local server: start the server (`../arma_watcher_server`,
  `scripts/dev.ps1`), then run `.\launchers\dev.ps1` here — cloud mode → `http://localhost:5000`
  as `dev@armawatcher.local` (matches the server's seeded dev customer).

## Conventions

- Python ≥3.11, **stdlib HTTP only** for networking (`urllib.request`) — no `requests`
  in the client. The server expects exactly these request shapes.
- DRY: the two inference backends share `QUEUE_PROMPT`/`DETECT_PROMPT`/`SCREEN_STATE_PROMPT`,
  the Pydantic schemas, and `_parse`/`_coerce_json`. Add new vision tasks in both backends.
- `arma-watcher`/`arma-watcher-gui` are the script entry points (`pyproject.toml`).
- Runs on Windows, Linux, and macOS. The package, GUI, and tests are cross-platform;
  Windows-only API calls in `gui.py` (`ctypes.windll` AppUserModelID, `.ico`
  `iconbitmap`) are guarded (`os.name == "nt"` / `try/except TclError`) so they no-op
  elsewhere. Windows ships the Inno Setup installer + `.bat`/`.ps1`/`.vbs` launchers;
  Linux/macOS use `launchers/install.sh` (mirrors `install.ps1`, adds a `.desktop`
  entry) and `launchers/run.sh` (mirrors `launch_gui.vbs`). All launchers live in
  `launchers/`; keep the per-platform pairs in sync. New launchers are picked up by
  self-update automatically (`updater._UPDATE_FILES` copies the whole `launchers/`
  folder), but add new packaged ones to the installer's `[Files]`/`[Icons]` in the `.iss`.

## Gotchas

- `.python-version` pins `3.14` while `pyproject.toml` says `requires-python >=3.11`;
  uv fetches the pinned interpreter. Don't assume they agree.
- `updater.py` overwrites the listed `_UPDATE_FILES` in place from the GitHub zip and
  `sys.exit(0)`s after — it never touches `~/.arma_watcher/config.json`.
- Monitor indices: `0` is the virtual all-monitors canvas; physical monitors are `1+`
  (`screenshot.list_monitors`). `SEARCHING_ARMA` scans `1..n`.
