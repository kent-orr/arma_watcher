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
  This is the monetized path: the user stores their *license key* (emailed at
  checkout), the proxy exchanges it for a short-lived opaque session token, inference
  is metered and rate-limited server-side. The *purchase email* is kept too, but only
  to start checkout and to recover a lost key — it is not a credential.

The client is deliberately ignorant of Stripe/DO — it only knows a proxy URL, a
license key (+ email for checkout/recovery), and the token dance. All payment/secrets
live in the server.

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
- **Give-up conditions** (set `_stop_reason`, then `stop()`): scanning bails after
  `_MAX_ARMA_ATTEMPTS` (5) fruitless monitor sweeps with an "Arma not found" message;
  once the queue hits the front (position ≤ 1) the run ends after
  `_FRONT_OF_QUEUE_TIMEOUT_S` (15 min) on the assumption the in-game transition was
  missed. `run()`'s tail logs `_stop_reason` instead of the bare "Stopped.".
- **Inference is pluggable**: `OllamaInference` and `CloudInference` expose the *same*
  three methods — `is_arma()`, `get_screen_state()`, `run()` — plus `unload()`.
  `make_inference(cfg)` picks one by `inference_mode`. Keep the interfaces identical;
  the watcher must not care which backend it holds. The backend is built once and
  cached (`_make_inference`) so the cloud session token survives across polls.
- **Structured output**: models are constrained to Pydantic schemas (`QueueInfo`,
  `ScreenState`, `_ArmaDetection`). Local Ollama enforces the JSON schema natively;
  cloud appends the schema to the prompt and `_coerce_json` trims stray prose before
  parsing. `_parse` has a regex fallback to salvage a bare integer position.
  - `ScreenState` classifies the screen into a **closed-set `Screen` enum** (`splash`,
    `main_menu`, `server_browser`, `in_queue`, `in_game`, `other`); `in_queue`/`in_game`
    are **derived properties** of that enum, so the states are mutually exclusive by
    construction and the watcher is untouched. The hard case the enum exists to nail is
    `server_browser` vs `in_queue` — the queue is a modal drawn *on top of* the browser,
    so the prompt gates `in_queue` on literally seeing the "waiting in the server queue"
    dialog + position number. The leading `queue_dialog_visible` field is a deliberate
    reasoning scaffold that stabilizes a lightweight model's choice — keep it.
  - All inference calls decode **greedily** (`_GREEDY`, `temperature=0`): classification
    is a deterministic task, so this is the single biggest reliability lever (it, not the
    prompt wording, is what locked in correct labels on `minicpm-v4.5`). Don't reintroduce
    default-temperature sampling on these calls.
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

- `POST /token` `{license_key}` → `{token, expires_at}`; `400/402/403` → `CloudAuthError`.
  **Email no longer mints a token** — the license key (emailed at checkout) does.
- `POST /v1/chat/completions` with `Authorization: Bearer <token>`, OpenAI-style body
  (`messages` with a `data:image/png;base64,...` image_url, `max_tokens`, `temperature`).
  The server **ignores** the client's model/prompt and injects its own — the client
  still sends a prompt + schema, but must not depend on them being honored verbatim.
- `POST /checkout` `{email, kind}` and `POST /recover` `{email}` use the email; `POST
  /portal` `{license_key}` uses the key. The GUI's *Show Key* reveals the stored key
  (copy to a new PC); *Email Me a New Key* calls `/recover` (rotates + emails a fresh key).
- Status codes the client depends on: `200` ok · `400` license key missing →
  `CloudAuthError` · `401/403` refresh token once then `CloudAuthError` · `402`
  `CloudAuthError` · `429` `CloudRateLimitError` (back off) · `413` payload too large.

## Config

`~/.arma_watcher/config.json` (see `DEFAULTS` in `config.py`). Never written by tests.
The cloud credential is `license_key`; `subscription_email` is kept only for checkout +
recovery. The proxy URL is **not** a config field — it's the hardcoded `config.SERVICE_URL`
(read everywhere via `config.service_url()`), since users never enter it. Three env vars
override config at load time **without persisting** — used by `dev.ps1`:
`ARMA_WATCHER_INFERENCE_MODE`, `ARMA_WATCHER_SUBSCRIPTION_EMAIL`, `ARMA_WATCHER_LICENSE_KEY`
(dev default `lk_dev_local`, matching the server seed). `config.save()` is careful not to
bake an active override into the file. Separately, `ARMA_WATCHER_PROXY_URL` overrides
`service_url()` so `dev.ps1` can point the client at a local server.

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

- `.python-version` pins `3.13` while `pyproject.toml` says `requires-python >=3.11`;
  uv fetches the pinned interpreter. Don't assume they agree. (The pin is just a
  chosen interpreter, not a hard requirement — bump it to any installed `>=3.11`.)
- `updater.py` overwrites the listed `_UPDATE_FILES` in place from the GitHub zip and
  `sys.exit(0)`s after — it never touches `~/.arma_watcher/config.json`.
- Monitor indices: `0` is the virtual all-monitors canvas; physical monitors are `1+`
  (`screenshot.list_monitors`). `SEARCHING_ARMA` scans `1..n`.
