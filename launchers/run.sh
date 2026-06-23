#!/usr/bin/env bash
# Linux/macOS launcher for Arma Watcher (GUI). Mirrors launch_gui.vbs / run.ps1.
# Requires: uv (https://astral.sh/uv) and Tk bindings (e.g. `sudo apt install python3-tk`).
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run arma-watcher-gui "$@"
