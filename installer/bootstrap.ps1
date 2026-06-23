# Arma Watcher - post-install bootstrap
# Invoked (hidden) by the Inno Setup installer after files are copied. Every line
# of progress is streamed to -LogFile, which the installer tails into its own
# wizard window, so the user never sees a separate console pop up.
#
# Installs uv (Python package manager), fetches Python, installs Ollama, runs
# uv sync, saves the chosen model to the app config, and pulls that model.

param(
    [string]$Model   = "qwen3.5:9b",
    [string]$LogFile = ""
)

$ErrorActionPreference = "Stop"

# Append a line to both stdout and the shared log file the installer tails.
# Retries briefly because the installer holds a (read) handle on the log every
# ~250ms; a momentary sharing collision should not drop the line.
function Log {
    param([string]$msg = "")
    Write-Output $msg
    if ($LogFile) {
        for ($i = 0; $i -lt 5; $i++) {
            try { Add-Content -Path $LogFile -Value $msg -Encoding ascii; break }
            catch { Start-Sleep -Milliseconds 50 }
        }
    }
}
function Step { param($m) Log ""; Log ("==> " + $m) }
function OK   { param($m) Log ("    OK  " + $m) }
function Warn { param($m) Log ("    >>  " + $m) }

function Refresh-Path {
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("PATH", "User") + ";" +
                (Join-Path $env:USERPROFILE ".local\bin")
}

# Persist the chosen model into the same config the GUI reads, merging with any
# existing config so we never clobber other settings.
function Save-Model {
    param([string]$model)
    $dir  = Join-Path $env:USERPROFILE ".arma_watcher"
    $path = Join-Path $dir "config.json"
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
    $cfg = @{}
    if (Test-Path $path) {
        try {
            $existing = Get-Content $path -Raw | ConvertFrom-Json
            foreach ($p in $existing.PSObject.Properties) { $cfg[$p.Name] = $p.Value }
        } catch {}
    }
    $cfg["model"] = $model
    # WriteAllText emits UTF-8 with no BOM, which Python's json.loads can read.
    [System.IO.File]::WriteAllText($path, ($cfg | ConvertTo-Json -Depth 6))
}

# The app root is the parent of installer\ (where this script lives).
$AppRoot = Split-Path -Parent $PSScriptRoot
Set-Location $AppRoot
Log ("Setting up Arma Watcher in: " + $AppRoot)

try {
    # uv ---------------------------------------------------------------------
    Step "Checking uv (Python package manager)..."
    Refresh-Path
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        OK "uv already installed."
    } else {
        Warn "uv not found - installing from astral.sh..."
        irm https://astral.sh/uv/install.ps1 | iex
        Refresh-Path
        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
            throw "uv install failed. See https://docs.astral.sh/uv/"
        }
        OK "uv installed."
    }

    # Python (managed by uv, pinned to .python-version) ----------------------
    Step "Installing Python..."
    uv python install *> $null
    OK "Python ready."

    # Ollama -----------------------------------------------------------------
    Step "Checking Ollama..."
    if (Get-Command ollama -ErrorAction SilentlyContinue) {
        OK "Ollama already installed."
    } else {
        Warn "Ollama not found - installing from ollama.com..."
        irm https://ollama.com/install.ps1 | iex
        Refresh-Path
        if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
            throw "Ollama install failed. See https://ollama.com"
        }
        OK "Ollama installed."
    }

    # Python dependencies ----------------------------------------------------
    Step "Installing Python dependencies (this can take a few minutes)..."
    uv sync 2>&1 | ForEach-Object { Log ([string]$_) }
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed." }
    OK "Dependencies installed."

    # Model ------------------------------------------------------------------
    if ($Model -and $Model -ne "none") {
        Step ("Saving model choice: " + $Model)
        Save-Model $Model
        OK "Saved to config."

        Step ("Downloading model " + $Model + " (this can be several GB - please wait)...")
        ollama pull $Model 2>&1 | ForEach-Object { Log ([string]$_) }
        if ($LASTEXITCODE -ne 0) {
            Warn "Model download did not finish. Arma Watcher will pull it on first launch."
        } else {
            OK ("Model " + $Model + " ready.")
        }
    } else {
        Step "No model selected - pick one anytime in the app's Settings panel."
    }

    Log ""
    Log "Arma Watcher is ready!"
    Log "Use the 'Arma Watcher' shortcut on your Desktop or Start Menu to open it."
    exit 0
}
catch {
    Log ""
    Log ("ERROR: " + $_.Exception.Message)
    exit 1
}
