# Dev launcher: run the GUI against a locally running arma_watcher_server.
#
# Sets cloud-mode overrides via environment only — your saved
# ~/.arma_watcher/config.json is read but never overwritten with these values.
# The default email matches arma_watcher_server's scripts/dev.ps1 seed, so the
# two repos line up out of the box. Start the server side first.
#
#   .\dev.ps1
#   .\dev.ps1 -ProxyUrl http://localhost:5000 -Email me@example.com
param(
    [string]$ProxyUrl = "http://localhost:5000",
    [string]$Email = "dev@armawatcher.local"
)
Set-Location $PSScriptRoot
$env:ARMA_WATCHER_INFERENCE_MODE = "cloud"
$env:ARMA_WATCHER_PROXY_URL = $ProxyUrl
$env:ARMA_WATCHER_SUBSCRIPTION_EMAIL = $Email
Write-Host "Launching GUI in cloud mode against $ProxyUrl as $Email (config.json untouched)..."
uv run python -m arma_watcher
