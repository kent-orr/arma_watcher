# This script lives in launchers/; update the repo root one level up.
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$repo    = "https://github.com/kent-orr/arma_watcher/archive/refs/heads/main.zip"
$zipFile = Join-Path $env:TEMP "arma_watcher_update.zip"
$extract = Join-Path $env:TEMP "arma_watcher_update"

Write-Host "Downloading latest release..."
try {
    Invoke-WebRequest -Uri $repo -OutFile $zipFile -UseBasicParsing
} catch {
    Write-Host "ERROR: Download failed — $_"
    Write-Host "Check your internet connection and try again."
    Write-Host "`nPress any key to close..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

Write-Host "Extracting..."
if (Test-Path $extract) { Remove-Item $extract -Recurse -Force }
Expand-Archive -Path $zipFile -DestinationPath $extract -Force

$src = Join-Path $extract "arma_watcher-main"

Write-Host "Copying updated files..."
Copy-Item (Join-Path $src "arma_watcher")    -Destination $RepoRoot -Recurse -Force
Copy-Item (Join-Path $src "pyproject.toml")  -Destination $RepoRoot -Force
# All launchers live under launchers/; refresh the whole folder in place.
Copy-Item (Join-Path $src "launchers\*")     -Destination $PSScriptRoot -Recurse -Force

Write-Host "Syncing dependencies..."
uv sync

Write-Host ""
Write-Host "Update complete."
Write-Host "`nPress any key to close..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
