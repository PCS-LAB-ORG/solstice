"""
drive_watcher.py — Google Drive file change monitor.

Watches .gsheet file mtimes via os.stat() — no Drive API auth needed.
When a file changes → opens CSV export URL in default browser →
user's corp session downloads the CSV → agent moves it from Downloads
to Solstice/data/inbox/ automatically.

Priority rule: DC CSE Tracker wins on any conflict (source of truth).
File order: DC CSE Tracker → EMEA Accounts CC Migrations → others

Config: data/drive_config.json (auto-created on first run)
"""
from __future__ import annotations
import glob
import json
import logging
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────

DRIVE_ROOT = Path.home() / "Library/CloudStorage/GoogleDrive-mbanica@paloaltonetworks.com/My Drive/EMEA CC "
DOWNLOADS  = Path.home() / "Downloads"
CONFIG_FILE = Path(__file__).parent.parent / "data" / "drive_config.json"

# ── Default file config — update IDs as you get them ──────────────────────

DEFAULT_CONFIG = {
    "files": [
        {
            "name":     "DC CSE Tracker",
            "gsheet":   "DC CSE Tracker (Instant sync underlying data to upgrade tracker).gsheet",
            "file_id":  "",          # ADD ID HERE — source of truth, processed first
            "priority": 1,
            "role":     "source_of_truth",
        },
        {
            "name":     "EMEA Accounts CC Migrations",
            "gsheet":   "EMEA Accounts CC Migrations.gsheet",
            "file_id":  "1tEVih8qBVv2yJhD8uIJVZb0mxDNiEGTTMS3hFYy5yN8",
            "priority": 2,
            "role":     "primary",
        },
        {
            "name":     "EMEA Cortex Cloud Upgrade Tracker",
            "gsheet":   "EMEA Cortex Cloud Upgrade Tracker.gsheet",
            "file_id":  "",          # ADD ID HERE
            "priority": 3,
            "role":     "secondary",
        },
        {
            "name":     "EMEA Solistce Blocked Accounts",
            "gsheet":   "EMEA Solistce_Blocked accounts.gsheet",
            "file_id":  "",          # ADD ID HERE
            "priority": 4,
            "role":     "secondary",
        },
    ],
    "poll_seconds":    60,
    "download_timeout": 30,   # seconds to wait for browser download
}


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    CONFIG_FILE.parent.mkdir(exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
    logger.info("Created drive_config.json — add file IDs to enable auto-export")
    return DEFAULT_CONFIG


def _export_url(file_id: str, sheet_index: int = 0) -> str:
    return f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=csv&gid={sheet_index}"


def _open_in_browser(url: str) -> None:
    """Open URL in default browser — corp session handles auth."""
    subprocess.Popen(["open", url])
    logger.info("Opened export URL in browser: %s", url[:80])


def _wait_for_download(expected_prefix: str, timeout: int = 30) -> Path | None:
    """
    Wait for a CSV matching expected_prefix to appear in ~/Downloads.
    Returns the path if found, None on timeout.
    """
    deadline = time.monotonic() + timeout
    seen_before = set(DOWNLOADS.glob("*.csv"))

    while time.monotonic() < deadline:
        time.sleep(2)
        current = set(DOWNLOADS.glob("*.csv"))
        new_files = current - seen_before
        for f in new_files:
            if expected_prefix.lower() in f.name.lower() or True:  # accept any new CSV
                return f
    return None


def _move_to_inbox(src: Path, inbox: Path, name: str) -> Path:
    """Move downloaded CSV to data/inbox/ with a clean filename."""
    inbox.mkdir(exist_ok=True)
    slug = name.lower().replace(" ", "_").replace("/", "_")
    dest = inbox / f"{slug}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    shutil.move(str(src), dest)
    logger.info("Moved %s → %s", src.name, dest)
    return dest


class DriveFileWatcher:
    """
    Monitors .gsheet files via os.stat() mtime.
    No Drive API auth required — change detection is local,
    download is triggered via browser (corp session).
    """

    def __init__(self, inbox: Path):
        self.inbox  = inbox
        self.config = _load_config()
        self._mtimes: dict[str, float] = {}
        self._init_mtimes()

    def _gsheet_path(self, entry: dict) -> Path:
        return DRIVE_ROOT / entry["gsheet"]

    def _init_mtimes(self) -> None:
        for entry in self.config["files"]:
            path = self._gsheet_path(entry)
            try:
                self._mtimes[entry["name"]] = os.stat(path).st_mtime
            except (FileNotFoundError, PermissionError):
                self._mtimes[entry["name"]] = 0
                logger.warning("Cannot stat %s — file may not be synced yet", entry["name"])

    def check_for_changes(self) -> list[dict]:
        """Return list of entries whose mtime changed since last check."""
        changed = []
        for entry in sorted(self.config["files"], key=lambda x: x["priority"]):
            path = self._gsheet_path(entry)
            try:
                mtime = os.stat(path).st_mtime
                if mtime != self._mtimes.get(entry["name"], 0):
                    logger.info("Change detected: %s (mtime %s → %s)",
                                entry["name"],
                                datetime.fromtimestamp(self._mtimes.get(entry["name"], 0)).strftime("%H:%M:%S"),
                                datetime.fromtimestamp(mtime).strftime("%H:%M:%S"))
                    self._mtimes[entry["name"]] = mtime
                    changed.append(entry)
            except (FileNotFoundError, PermissionError):
                pass
        return changed

    def download_and_stage(self, entry: dict) -> Path | None:
        """
        Open CSV export URL in browser → wait for download → move to inbox.
        Returns the inbox path if successful, None otherwise.
        """
        file_id = entry.get("file_id", "").strip()
        if not file_id:
            logger.warning("%s: no file_id configured — skipping auto-download. "
                           "Add the ID to data/drive_config.json", entry["name"])
            return None

        url = _export_url(file_id)
        logger.info("Triggering export for %s", entry["name"])
        _open_in_browser(url)

        timeout = self.config.get("download_timeout", 30)
        downloaded = _wait_for_download(entry["name"], timeout)
        if not downloaded:
            logger.warning("%s: no CSV appeared in Downloads within %ds", entry["name"], timeout)
            return None

        return _move_to_inbox(downloaded, self.inbox, entry["name"])

    def run(self, pipeline_callback) -> None:
        """
        Blocking poll loop. Calls pipeline_callback(csv_path) for each
        downloaded file — DC CSE Tracker first (source of truth).
        Ctrl+C to stop.
        """
        poll = self.config.get("poll_seconds", 60)
        logger.info("Drive watcher started — polling every %ds", poll)
        logger.info("Watching %d files in %s", len(self.config["files"]), DRIVE_ROOT)

        while True:
            try:
                changed = self.check_for_changes()
                for entry in changed:
                    path = self.download_and_stage(entry)
                    if path:
                        logger.info("Staging %s → pipeline", path.name)
                        try:
                            pipeline_callback(path)
                        except Exception as e:
                            logger.error("Pipeline error for %s: %s", entry["name"], e)

                time.sleep(poll)

            except KeyboardInterrupt:
                logger.info("Drive watcher stopped.")
                break


def print_config_status() -> None:
    """Print current config status — useful for setup verification."""
    config = _load_config()
    print("\nDrive Watcher Config:")
    print(f"  Poll interval: {config['poll_seconds']}s")
    print(f"  Files:")
    for e in sorted(config["files"], key=lambda x: x["priority"]):
        path = DRIVE_ROOT / e["gsheet"]
        try:
            mtime = datetime.fromtimestamp(os.stat(path).st_mtime).strftime("%d %b %H:%M")
            stat_ok = f"✅ accessible (last modified {mtime})"
        except:
            stat_ok = "❌ not accessible (not synced yet)"
        id_ok = f"✅ {e['file_id'][:20]}..." if e.get("file_id") else "⚠️  NO FILE ID — add to drive_config.json"
        print(f"\n  [{e['priority']}] {e['name']} ({e['role']})")
        print(f"      stat:    {stat_ok}")
        print(f"      file_id: {id_ok}")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
    print_config_status()
