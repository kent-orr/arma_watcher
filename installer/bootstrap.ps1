# Arma Watcher - post-install bootstrap
# Invoked by the Inno Setup installer after files are copied.
# Installs uv (Python package manager), Ollama, fetches Python, and syncs
# dependencies into an isolated environment inside the install folder.
# Shortcuts are created by the installer, not here.

$ErrorActionPreference = "Stop"

function Write-Step { param($msg) Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-OK   { param($msg) Write-Host "    OK  $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "    >>  $msg" -ForegroundColor Yellow }
function Write-Err  { param($msg) Write-Host "`nERROR: $msg" -ForegroundColor Red }

function Refresh-Path {
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("PATH", "User") + ";" +
                (Join-Path $env:USERPROFILE ".local\bin")
}

# Run from the install folder (the directory this script lives in is installer\,
# the app root is its parent).
$AppRoot = Split-Path -Parent $PSScriptRoot
Set-Location $AppRoot

Write-Host "Setting up Arma Watcher in: $AppRoot" -ForegroundColor White

try {
    # uv ---------------------------------------------------------------------
    Write-Step "Checking uv (Python package manager)..."
    Refresh-Path
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Write-OK "uv already installed."
    } else {
        Write-Warn "uv not found - installing from astral.sh..."
        irm https://astral.sh/uv/install.ps1 | iex
        Refresh-Path
        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
            Write-Err "uv install failed. See https://docs.astral.sh/uv/"
            exit 1
        }
        Write-OK "uv installed."
    }

    # Python (managed by uv, pinned to .python-version) ----------------------
    Write-Step "Checking Python..."
    uv python install | Out-Null
    Write-OK "Python ready."

    # Ollama -----------------------------------------------------------------
    Write-Step "Checking Ollama..."
    if (Get-Command ollama -ErrorAction SilentlyContinue) {
        Write-OK "Ollama already installed."
    } else {
        Write-Warn "Ollama not found - installing from ollama.com..."
        irm https://ollama.com/install.ps1 | iex
        Refresh-Path
        if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
            Write-Err "Ollama install failed. See https://ollama.com"
            exit 1
        }
        Write-OK "Ollama installed."
    }

    # Python dependencies ----------------------------------------------------
    Write-Step "Installing Python dependencies (this can take a few minutes)..."
    uv sync
    if ($LASTEXITCODE -ne 0) {
        Write-Err "uv sync failed."
        exit 1
    }
    Write-OK "Dependencies installed."

    Write-Host ""
    Write-Host "Arma Watcher is ready!" -ForegroundColor Green
    Write-Host "    Use the 'Arma Watcher' shortcut on your Desktop or Start Menu to open it." -ForegroundColor White
    Write-Host ""
    Start-Sleep -Seconds 3
    exit 0
}
catch {
    Write-Err $_
    Write-Host ""
    Write-Host "Setup did not complete. You can retry by re-running the installer," -ForegroundColor Yellow
    Write-Host "or open the install folder and run install.bat manually." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Press any key to close..." -ForegroundColor White
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}
