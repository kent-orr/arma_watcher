# Arma Watcher

Monitors your Arma Reforger screen, detects when you enter a server queue, and sends Discord notifications with your position and estimated wait time. Uses a local vision model via Ollama — no cloud API required.

---

## Requirements

- Windows 10/11
- A GPU with at least **1 GB VRAM** (6.6 GB recommended for the default model)
- Arma Reforger running on any connected monitor
- *(Optional)* A Discord webhook URL for notifications

---

## Installation

Double-click **`install.bat`** in the repo root (or right-click → *Run as administrator* if you hit permission errors).

The installer runs through these steps automatically:

### 1 — uv (Python package manager)

`uv` is used to manage Python and the project's dependencies. If it isn't already installed, the script downloads and installs it from [astral.sh](https://astral.sh/uv/).

### 2 — Python

`uv` ensures the correct Python version is available. Nothing to do here.

### 3 — Ollama

Ollama runs the local vision model. If it isn't already installed, the script downloads and runs the official installer from [ollama.com](https://ollama.com).

### 4 — Python dependencies

`uv sync` installs all Python packages into an isolated virtual environment inside the repo.

### 5 — First-time setup wizard

An interactive prompt collects your preferences and saves them to `C:\Users\<you>\.arma_watcher\config.json`.

---

## Setup Wizard — step by step

```
=== Arma Watcher — First-time Setup ===
Press Enter to accept the default for each option.
```

#### Model selection

```
  Select a model:

    1) qwen3.5:0.8b     1.0 GB VRAM
    2) qwen3.5:2b       2.7 GB VRAM
    3) qwen3.5:4b       3.4 GB VRAM
    4) qwen3.5:9b       6.6 GB VRAM  (recommended)

  Enter 1-4 [4]:
```

Pick the largest model your GPU can fit. The default (`4`, qwen3.5:9b) gives the best accuracy. On lower-VRAM cards choose `1` or `2`.

#### Pull the model

```
  Pull qwen3.5:9b now? This may take a while [Y/n]:
```

Press **Enter** (or type `Y`) to download the model immediately — this can be several gigabytes. Type `n` to skip and pull it manually later:

```
ollama pull qwen3.5:9b
```

The watcher will not start until Ollama is running and the model has been pulled. If you skipped the pull, do it before launching.

#### Discord webhook URL

```
Discord webhook URL [none]:
```

Paste a Discord incoming webhook URL to receive queue position updates in a channel. Leave blank to disable notifications.

To create one: *Discord channel settings → Integrations → Webhooks → New Webhook → Copy Webhook URL*.

#### Discord user ID *(optional)*

```
Discord user ID for @mentions (optional — enable Developer Mode, right-click your name, Copy User ID) [none]:
```

Paste your numeric Discord user ID to be @mentioned directly in queue notifications. Leave blank to send notifications without a ping.

To find your ID: *Discord Settings → Advanced → enable Developer Mode*, then right-click your username anywhere and select **Copy User ID**.

#### Monitor index

```
Monitor index (leave blank to auto-detect) [none]:
```

Leave blank and the watcher will scan all monitors to find Arma Reforger automatically. Enter a number (e.g. `0`, `1`, `2`) to pin it to a specific display.

#### Poll intervals

```
Queue poll interval in seconds [20]:
Detection retry interval in seconds [5]:
```

- **Queue poll interval** — how often (in seconds) the watcher checks your position once you are in a queue. Default: 20.
- **Detection retry interval** — how often (in seconds) the watcher looks for Arma / a queue screen before one is found. Default: 5.

Press **Enter** to accept both defaults.

---

After the wizard completes, a **desktop shortcut** named *Arma Watcher* is created. Double-click it any time to start monitoring.

---

## Running

Double-click the **Arma Watcher** desktop shortcut, or run from the repo root:

```bat
run.bat
```

Or directly via uv:

```bat
uv run arma-watcher
```

### What you'll see

```
[21:45:46] Discord webhook OK.
[21:46:09] Waiting for queue...
[21:46:21] Position: 47 | My Server | Rate: -- | ETA: --
[21:47:21] Position: 43 | My Server | Rate: 4.0/min | ETA: ~11min
```

Once you enter the game the watcher unloads the model from VRAM and sends a final Discord notification.

### Discord notifications

Instead of sending a message on every queue poll, the watcher sends a small set of milestone pings so your channel doesn't get spammed:

| Event | Message |
|---|---|
| Queue detected | `@you You're in the queue at position 47 on My Server. \| ETA: ~12min` |
| Position ≤ 30 | `Still waiting — 30 to go. \| Position: 28 \| Server: ... \| ETA: ~7min` |
| Position ≤ 20 | `Getting closer — 20 to go. \| ...` |
| Position ≤ 10 | `Only 10 left! \| ...` |
| Position ≤ 5 | `Almost there — 5 to go! \| ...` |
| Position ≤ 3 | `3 more! \| ...` |
| Position ≤ 1 | `Next up! \| ...` |
| In game | `@you You're in! Get on the server.` |

Milestones that the queue starts below are skipped (e.g. if you join at position 8, the 30 and 20 messages are never sent). The `@you` ping is only included if a Discord user ID is configured.

Press **Ctrl+C** at any time to stop. The model is unloaded from VRAM automatically on exit.

### Ollama not running?

If Ollama isn't started when the watcher launches, it waits and retries automatically:

```
[21:38:59] Ollama is not running. Start Ollama and this watcher will resume automatically. Retrying in 15s...
```

Start Ollama and the watcher will continue without needing a restart.

---

## Updating

To pull the latest version without needing git, double-click **`update.bat`** in the repo root.

It will:
1. Download the latest `main` branch zip from GitHub
2. Replace the `arma_watcher/` package files and scripts
3. Run `uv sync` to update dependencies

Your config (`C:\Users\<you>\.arma_watcher\config.json`) is never touched.

---

## Re-running setup

To change any setting (model, Discord URL, monitor, intervals):

```bat
uv run arma-watcher --setup
```

Config is stored at `C:\Users\<you>\.arma_watcher\config.json`.

---

## Command-line overrides

Any config value can be overridden at launch without re-running setup:

| Flag | Description |
|---|---|
| `--monitor N` | Use monitor index N |
| `--interval N` | Queue poll interval in seconds |
| `--detect-interval N` | Detection retry interval in seconds |
| `--discord-webhook URL` | Discord webhook URL |
| `--setup` | Re-run the setup wizard |
