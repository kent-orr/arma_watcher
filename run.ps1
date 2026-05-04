Set-Location $PSScriptRoot
uv run arma-watcher
Write-Host "`nPress any key to close..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
