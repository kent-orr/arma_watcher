# Installer

Builds `ArmaWatcherSetup.exe` — a point-and-click Windows installer.

## Files

| File | Purpose |
|---|---|
| `arma_watcher.iss` | [Inno Setup](https://jrsoftware.org/isinfo.php) script. Bundles the app, runs the bootstrap, creates shortcuts. Per-user install (no admin / UAC). |
| `bootstrap.ps1` | Runs after files are copied: installs uv, fetches Python, installs Ollama, runs `uv sync`. |

## Cut a release (recommended)

The GitHub Actions workflow `.github/workflows/build-installer.yml` builds the
installer on a Windows runner and attaches it to a Release automatically:

```bash
git tag v0.1.0
git push origin v0.1.0
```

The version baked into the installer comes from the tag (`v0.1.0` → `0.1.0`).
The download page and README link to
`releases/latest/download/ArmaWatcherSetup.exe`, so a new release is picked up
with no further changes. You can also trigger the workflow manually
("Run workflow") to build the `.exe` as an artifact without publishing.

## Build locally

1. Install [Inno Setup 6](https://jrsoftware.org/isdl.php).
2. From the repo root:

   ```powershell
   & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "/DMyAppVersion=0.1.0" installer\arma_watcher.iss
   ```

3. Output lands in `dist\ArmaWatcherSetup.exe`.

## Download page (GitHub Pages)

`docs/index.html` is the landing page. Enable it once in the repo:
**Settings → Pages → Source: Deploy from a branch → `main` / `/docs`**.
It then serves at `https://kent-orr.github.io/arma_watcher/`.
