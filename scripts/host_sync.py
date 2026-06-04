#!/usr/bin/env python3
"""
host_sync.py — downloads XSUP Tracker and COE Tracker xlsx files to data/
Runs on the Mac host (NOT inside Docker) where googleusercontent.com CDN is reachable.
Scheduled via launchd every 30 minutes. Also called by setup.sh on first run.

Usage:
    python3 scripts/host_sync.py
"""

import json
import subprocess
import sys
import warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore")

REPO_DIR = Path(__file__).parent.parent
DATA_DIR = REPO_DIR / "data"
LOG_FILE = REPO_DIR / "data" / "host_sync.log"

GDRIVE_WORK = Path.home() / "Library/CloudStorage"

SOURCES = [
    {
        "name": "XSUP Tracker",
        "gsheet_path": "Cortex Cloud Work/Cortex Cloud Open XSUPs with TAC.gsheet",
        "dest": DATA_DIR / "xsup_tracker.xlsx",
        "fmt": "xlsx",
    },
    {
        "name": "COE Tracker",
        "gsheet_path": "Cortex Cloud Work/Central Technical COE Tracker.gsheet",
        "dest": DATA_DIR / "coe_tracker.xlsx",
        "fmt": "xlsx",
    },
]


def find_gdrive_root() -> Path | None:
    """Find the PANW Google Drive mount."""
    for entry in GDRIVE_WORK.iterdir():
        if entry.name.startswith("GoogleDrive-") and entry.name.endswith(
            "@paloaltonetworks.com"
        ):
            return entry / "My Drive"
    return None


def get_token() -> str | None:
    try:
        return subprocess.check_output(
            ["gcloud", "auth", "application-default", "print-access-token"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception as e:
        log(f"ADC token failed: {e}")
        return None


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def download(source: dict, drive_root: Path, token: str) -> bool:
    gsheet_file = drive_root / source["gsheet_path"]
    try:
        file_id = json.loads(gsheet_file.read_text())["doc_id"]
    except Exception as e:
        log(f"  {source['name']}: cannot read .gsheet — {e}")
        return False

    url = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format={source['fmt']}"
    dest = source["dest"]

    try:
        import urllib.request

        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        # Stream to disk in chunks with 30s timeout per chunk
        with urllib.request.urlopen(req, timeout=30) as r:
            tmp = Path(str(dest) + ".tmp")
            with open(tmp, "wb") as fh:
                while chunk := r.read(256 * 1024):
                    fh.write(chunk)
            tmp.replace(dest)
        content_size = dest.stat().st_size
        log(f"  {source['name']}: ✅ {content_size:,} bytes → {dest.name}")
        return True
    except Exception as e:
        age = ""
        if dest.exists():
            import time as _t

            age_h = (_t.time() - dest.stat().st_mtime) / 3600
            age = (
                f" (cached {age_h:.0f}h ago)"
                if age_h < 48
                else f" (cached {age_h / 24:.0f}d ago)"
            )
        log(
            f"  {source['name']}: ⚠️ download failed — {str(e)[:60]}{age} — using cached file"
        )
        return False


def main() -> None:
    log("=== host_sync start ===")

    drive_root = find_gdrive_root()
    if not drive_root:
        log("Google Drive not mounted — exiting")
        sys.exit(1)

    token = get_token()
    if not token:
        log("No ADC token — exiting")
        sys.exit(1)

    DATA_DIR.mkdir(exist_ok=True)
    ok = sum(download(s, drive_root, token) for s in SOURCES)
    log(f"=== host_sync done: {ok}/{len(SOURCES)} succeeded ===")


if __name__ == "__main__":
    main()
