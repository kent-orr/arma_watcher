# Arma Watcher - Windows Setup
# Run from the repo root: .\install.bat

$ErrorActionPreference = "Stop"

function Write-Step { param($msg) Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-OK   { param($msg) Write-Host "    OK  $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "    >>  $msg" -ForegroundColor Yellow }

function Refresh-Path {
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("PATH", "User")
}

# uv
Write-Step "Checking uv (Python package manager)..."
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-OK "uv already installed."
} else {
    Write-Warn "uv not found - installing from astral.sh..."
    irm https://astral.sh/uv/install.ps1 | iex
    Refresh-Path
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host "`nERROR: uv install failed. See https://docs.astral.sh/uv/" -ForegroundColor Red
        exit 1
    }
    Write-OK "uv installed."
}

# Python (managed by uv, pinned to .python-version)
Write-Step "Checking Python..."
uv python install | Out-Null
Write-OK "Python ready."

# Ollama
Write-Step "Checking Ollama..."
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Write-OK "Ollama already installed."
} else {
    Write-Warn "Ollama not found - installing from ollama.com..."
    irm https://ollama.com/install.ps1 | iex
    Refresh-Path
    if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
        Write-Host "`nERROR: Ollama install failed. See https://ollama.com" -ForegroundColor Red
        exit 1
    }
    Write-OK "Ollama installed."
}

# Python dependencies
Write-Step "Installing Python dependencies..."
uv sync
Write-OK "Dependencies installed."

# Desktop shortcut
Write-Step "Creating desktop shortcut..."
$launcher  = Join-Path $PSScriptRoot "launch_gui.vbs"
$shortcut  = Join-Path ([Environment]::GetFolderPath("Desktop")) "Arma Watcher.lnk"
$wsh       = New-Object -ComObject WScript.Shell
$lnk       = $wsh.CreateShortcut($shortcut)
$lnk.TargetPath       = "wscript.exe"
$lnk.Arguments        = "`"$launcher`""
$lnk.WorkingDirectory = $PSScriptRoot
$lnk.Description      = "Start Arma Watcher"
$iconPath = Join-Path $PSScriptRoot "arma_watcher\assets\icon.ico"
if (Test-Path $iconPath) { $lnk.IconLocation = "$iconPath,0" }
$lnk.Save()
Write-OK "Shortcut created."

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host "    Double-click 'Arma Watcher' on your Desktop to open the GUI." -ForegroundColor White
Write-Host "    Configure your Discord webhook and model in the Settings panel," -ForegroundColor White
Write-Host "    then click Start." -ForegroundColor White
Write-Host ""
