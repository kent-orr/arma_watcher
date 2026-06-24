# Dev launcher: run the GUI against a locally running arma_watcher_server.
#
# Sets cloud-mode overrides via environment only — your saved
# ~/.arma_watcher/config.json is read but never overwritten with these values.
# The default email + license key match arma_watcher_server's scripts/dev.ps1
# seed (DEV_LICENSE_KEY), so the two repos line up out of the box. The license
# key — not the email — is what grants inference. Start the server side first.
#
#   .\launchers\dev.ps1
#   .\launchers\dev.ps1 -ProxyUrl http://localhost:5000 -Email me@example.com
param(
    [string]$ProxyUrl = "http://localhost:5000",
    [string]$Email = "dev@armawatcher.local",
    [string]$LicenseKey = "lk_dev_local"
)
Set-Location (Split-Path -Parent $PSScriptRoot)
$env:ARMA_WATCHER_INFERENCE_MODE = "cloud"
$env:ARMA_WATCHER_PROXY_URL = $ProxyUrl
$env:ARMA_WATCHER_SUBSCRIPTION_EMAIL = $Email
$env:ARMA_WATCHER_LICENSE_KEY = $LicenseKey
Write-Host "Launching GUI in cloud mode against $ProxyUrl as $Email (config.json untouched)..."
uv run python -m arma_watcher
