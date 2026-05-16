import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

_REPO = "kent-orr/arma_watcher"
_BRANCH = "main"
_API_URL = f"https://api.github.com/repos/{_REPO}/commits/{_BRANCH}"
_ZIP_URL = f"https://github.com/{_REPO}/archive/refs/heads/{_BRANCH}.zip"
_INSTALL_DIR = Path(__file__).parent.parent.resolve()
_SHA_FILE = Path.home() / ".arma_watcher" / "installed_sha"
_UPDATE_FILES = ["arma_watcher", "pyproject.toml", "run.ps1", "run.bat", "update.ps1", "update.bat"]


def _remote_sha() -> str | None:
    try:
        req = urllib.request.Request(
            _API_URL,
            headers={"User-Agent": "ArmaWatcher/1.0", "Accept": "application/vnd.github.v3+json"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read()).get("sha")
    except Exception:
        return None


def _local_sha() -> str | None:
    try:
        return _SHA_FILE.read_text().strip() or None
    except FileNotFoundError:
        return None


def _save_sha(sha: str) -> None:
    _SHA_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SHA_FILE.write_text(sha)


def _apply_update(remote_sha: str) -> None:
    print("Downloading update...")
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = Path(tmpdir) / "update.zip"
        with urllib.request.urlopen(_ZIP_URL, timeout=60) as resp, zip_path.open("wb") as f:
            shutil.copyfileobj(resp, f)

        print("Extracting...")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmpdir)

        src = Path(tmpdir) / f"arma_watcher-{_BRANCH}"
        print("Copying files...")
        for name in _UPDATE_FILES:
            s, d = src / name, _INSTALL_DIR / name
            if s.is_dir():
                if d.exists():
                    shutil.rmtree(d)
                shutil.copytree(s, d)
            elif s.is_file():
                shutil.copy2(s, d)

    print("Syncing dependencies...")
    subprocess.run(["uv", "sync"], cwd=_INSTALL_DIR)
    _save_sha(remote_sha)
    print("\nUpdate complete. Please restart the watcher.")
    sys.exit(0)


def check_for_updates() -> None:
    remote = _remote_sha()
    if remote is None:
        return  # offline or GitHub unreachable — skip silently

    local = _local_sha()
    if local is None:
        # First launch — no baseline yet. Record current remote as installed and move on.
        _save_sha(remote)
        return

    if local == remote:
        return  # already up to date

    print(f"\nUpdate available: {local[:7]} → {remote[:7]}")
    try:
        answer = input("Update now? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if answer == "y":
        _apply_update(remote)
