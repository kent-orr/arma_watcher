Set-Location $PSScriptRoot
uv run python -m arma_watcher
Write-Host "`nPress any key to close..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
