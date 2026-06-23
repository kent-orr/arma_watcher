#!/usr/bin/env bash
# Arma Watcher — Linux/macOS setup. Mirrors install.ps1.
# Run from anywhere:  ./launchers/install.sh
set -euo pipefail

SELF="$(cd "$(dirname "$0")" && pwd)"     # launchers/
DIR="$(cd "$SELF/.." && pwd)"             # repo root
cd "$DIR"

step() { printf '\n==> %s\n' "$1"; }
ok()   { printf '    OK  %s\n' "$1"; }
warn() { printf '    >>  %s\n' "$1"; }
die()  { printf '\nERROR: %s\n' "$1" >&2; exit 1; }

# ── uv (Python package manager) ──────────────────────────────────────────────
step "Checking uv (Python package manager)..."
if command -v uv >/dev/null 2>&1; then
    ok "uv already installed."
else
    warn "uv not found — installing from astral.sh..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # uv installs to ~/.local/bin; make it visible for the rest of this script.
    export PATH="$HOME/.local/bin:$PATH"
    command -v uv >/dev/null 2>&1 || die "uv install failed. See https://docs.astral.sh/uv/"
    ok "uv installed."
fi

# ── Python (managed by uv, pinned to .python-version) ────────────────────────
step "Checking Python..."
uv python install >/dev/null
ok "Python ready."

# ── Ollama (local vision model; skip if using cloud mode) ────────────────────
step "Checking Ollama..."
if command -v ollama >/dev/null 2>&1; then
    ok "Ollama already installed."
else
    warn "Ollama not found — installing from ollama.com..."
    if curl -fsSL https://ollama.com/install.sh | sh; then
        command -v ollama >/dev/null 2>&1 && ok "Ollama installed." \
            || warn "Ollama installed but not on PATH yet — open a new shell."
    else
        warn "Ollama install skipped/failed. Install manually from https://ollama.com"
        warn "(not required if you use cloud inference mode)."
    fi
fi

# ── Python dependencies ──────────────────────────────────────────────────────
step "Installing Python dependencies..."
uv sync
ok "Dependencies installed."

# ── Desktop entry (freedesktop .desktop launcher) ────────────────────────────
step "Creating desktop entry..."
APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$APPS_DIR"
ICON="$DIR/arma_watcher/assets/icon.ico"
cat > "$APPS_DIR/arma-watcher.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Arma Watcher
Comment=Watch the Arma Reforger server queue and get Discord pings
Exec=$SELF/run.sh
Path=$DIR
Icon=$ICON
Terminal=false
Categories=Game;Utility;
EOF
chmod +x "$APPS_DIR/arma-watcher.desktop"
update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
ok "Desktop entry created (search 'Arma Watcher' in your launcher)."

cat <<'EOF'

Setup complete!
    Launch 'Arma Watcher' from your applications menu, or run ./launchers/run.sh
    Configure your Discord webhook and model in the Settings panel,
    then click Start.
EOF
