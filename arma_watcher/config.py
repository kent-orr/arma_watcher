import json
import os
import pathlib
import platform
import shutil
import subprocess

CONFIG_PATH = pathlib.Path.home() / ".arma_watcher" / "config.json"

# Env vars that override the saved config at load time. Used by the dev launcher
# (dev.ps1) to point the GUI at a local arma_watcher_server for integration
# testing without editing — or persisting anything to — config.json.
_ENV_OVERRIDES = {
    "inference_mode": "ARMA_WATCHER_INFERENCE_MODE",
    "proxy_url": "ARMA_WATCHER_PROXY_URL",
    "subscription_email": "ARMA_WATCHER_SUBSCRIPTION_EMAIL",
}

DEFAULTS = {
    "discord_webhook": None,
    "discord_user_id": None,
    "model": "qwen3.5:9b",
    "monitor": None,
    "interval": 20,
    "detect_interval": 5,
    # Inference backend: "local" runs the model on the user's own VRAM via
    # Ollama; "cloud" routes screenshots through the subscription proxy.
    "inference_mode": "local",
    "proxy_url": None,           # e.g. https://my-service.example.com
    "subscription_email": None,  # purchase email, exchanged for a session token
}

_MODELS = [
    ("qwen3.5:0.8b", "1.0 GB VRAM"),
    ("qwen3.5:2b",   "2.7 GB VRAM"),
    ("qwen3.5:4b",   "3.4 GB VRAM"),
    ("qwen3.5:9b",   "6.6 GB VRAM  (recommended)"),
]

_PROMPTS = [
    ("discord_webhook", "Discord webhook URL", None),
    ("discord_user_id", "Discord user ID for @mentions (optional — enable Developer Mode, right-click your name, Copy User ID)", None),
    ("monitor", "Monitor index (leave blank to auto-detect)", None),
    ("interval", "Queue poll interval in seconds", 20),
    ("detect_interval", "Detection retry interval in seconds", 5),
]


def _apply_env_overrides(cfg: dict) -> dict:
    for key, env in _ENV_OVERRIDES.items():
        val = os.environ.get(env)
        if val:
            cfg[key] = val
    return cfg


def load() -> dict:
    if CONFIG_PATH.exists():
        try:
            return _apply_env_overrides({**DEFAULTS, **json.loads(CONFIG_PATH.read_text())})
        except Exception:
            pass
    return _apply_env_overrides(dict(DEFAULTS))


def save(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if CONFIG_PATH.exists():
        try:
            existing = json.loads(CONFIG_PATH.read_text())
        except Exception:
            existing = {}
    to_write = dict(cfg)
    # Don't let a dev env override leak into config.json: for any key currently
    # supplied by an override, keep the real on-disk value (or omit it).
    for key, env in _ENV_OVERRIDES.items():
        if os.environ.get(env):
            if key in existing:
                to_write[key] = existing[key]
            else:
                to_write.pop(key, None)
    CONFIG_PATH.write_text(json.dumps(to_write, indent=2))


def _ensure_ollama() -> None:
    if shutil.which("ollama"):
        print("  Ollama is already installed.")
        return

    print("\n  Ollama was not found on this machine.")
    print("  It is required to run the local vision model.\n")

    if platform.system() != "Windows":
        print("  Automatic install is only supported on Windows.")
        print("  Visit https://ollama.com to install manually, then re-run setup.")
        return

    consent = input("  Install Ollama now? This will run the official installer from ollama.com [y/N]: ").strip().lower()
    if consent != "y":
        print("  Skipping Ollama install. Run setup again or install manually from ollama.com.")
        return

    print("  Running: irm https://ollama.com/install.ps1 | iex\n")
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "irm https://ollama.com/install.ps1 | iex"],
        check=False,
    )
    if result.returncode == 0:
        print("\n  Ollama installed successfully.")
    else:
        print(f"\n  Installer exited with code {result.returncode}. Check output above for errors.")


def _pick_model() -> str:
    print("  Select a model:\n")
    for i, (name, vram) in enumerate(_MODELS, 1):
        print(f"    {i}) {name:<16} {vram}")
    print()
    default_idx = len(_MODELS)  # qwen3.5:9b
    while True:
        raw = input(f"  Enter 1-{len(_MODELS)} [{default_idx}]: ").strip()
        if not raw:
            return _MODELS[default_idx - 1][0]
        if raw.isdigit() and 1 <= int(raw) <= len(_MODELS):
            return _MODELS[int(raw) - 1][0]
        print(f"  Please enter a number between 1 and {len(_MODELS)}.")


def _pull_model(model: str) -> None:
    if not shutil.which("ollama"):
        return
    consent = input(f"  Pull {model} now? This may take a while [Y/n]: ").strip().lower()
    if consent == "n":
        print(f"  Skipping. Run `ollama pull {model}` before starting the watcher.")
        return
    print(f"  Running: ollama pull {model}\n")
    subprocess.run(["ollama", "pull", model], check=False)


def run_setup(force: bool = False) -> dict:
    if CONFIG_PATH.exists() and not force:
        return load()

    print("\n=== Arma Watcher — First-time Setup ===")
    print("Press Enter to accept the default for each option.")

    _ensure_ollama()
    print()

    cfg = {}
    cfg["model"] = _pick_model()
    _pull_model(cfg["model"])
    print()

    for key, label, default in _PROMPTS:
        default_display = f" [{default}]" if default is not None else " [none]"
        raw = input(f"{label}{default_display}: ").strip()

        if not raw:
            cfg[key] = default
            continue

        # coerce integers for numeric fields
        if key in ("monitor", "interval", "detect_interval"):
            try:
                cfg[key] = int(raw)
            except ValueError:
                print(f"  Invalid number, using default ({default}).")
                cfg[key] = default
        else:
            cfg[key] = raw or default

    save(cfg)
    print(f"\nConfig saved to {CONFIG_PATH}\n")
    return cfg
