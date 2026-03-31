"""Tests for drive_watcher.py — mtime-based Google Drive change detection."""
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_drive(tmp_path):
    """Fake EMEA CC folder with .gsheet stubs."""
    folder = tmp_path / "EMEA CC"
    folder.mkdir()
    for name in [
        "DC CSE Tracker (Instant sync underlying data to upgrade tracker).gsheet",
        "EMEA Accounts CC Migrations.gsheet",
        "EMEA Cortex Cloud Upgrade Tracker.gsheet",
    ]:
        stub = folder / name
        stub.write_text(json.dumps({"doc_id": f"fake_id_{name[:8]}", "url": "https://example.com"}))
    return folder


@pytest.fixture
def tmp_inbox(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    return inbox


@pytest.fixture
def tmp_downloads(tmp_path):
    dl = tmp_path / "Downloads"
    dl.mkdir()
    return dl


@pytest.fixture
def watcher(tmp_drive, tmp_inbox, tmp_path):
    """DriveFileWatcher with patched paths — patches stay active for entire test."""
    config = {
        "files": [
            {
                "name": "DC CSE Tracker",
                "gsheet": "DC CSE Tracker (Instant sync underlying data to upgrade tracker).gsheet",
                "file_id": "dc_fake_id_111",
                "priority": 1,
                "role": "source_of_truth",
            },
            {
                "name": "EMEA Accounts CC Migrations",
                "gsheet": "EMEA Accounts CC Migrations.gsheet",
                "file_id": "emea_fake_id_222",
                "priority": 2,
                "role": "primary",
            },
        ],
        "poll_seconds": 1,
        "download_timeout": 2,
    }
    config_file = tmp_path / "drive_config.json"
    config_file.write_text(json.dumps(config))

    from agent.drive_watcher import DriveFileWatcher
    with patch("agent.drive_watcher.DRIVE_ROOT", tmp_drive), \
         patch("agent.drive_watcher.CONFIG_FILE", config_file):
        w = DriveFileWatcher(inbox=tmp_inbox)
        yield w, tmp_drive, tmp_inbox  # yield keeps patches active during test


# ── Tests ────────────────────────────────────────────────────────────────────

def test_watcher_initialises_mtimes(watcher):
    """Watcher records initial mtimes for all configured files."""
    w, drive, inbox = watcher
    assert "DC CSE Tracker" in w._mtimes
    assert "EMEA Accounts CC Migrations" in w._mtimes
    assert w._mtimes["DC CSE Tracker"] > 0


def test_no_change_returns_empty(watcher):
    """check_for_changes returns [] when no files have been modified."""
    w, drive, inbox = watcher
    changed = w.check_for_changes()
    assert changed == []


def test_mtime_change_detected(watcher):
    """check_for_changes detects when a .gsheet file mtime changes."""
    w, drive, inbox = watcher
    # Touch the DC CSE Tracker file (simulate Drive sync)
    stub = drive / "DC CSE Tracker (Instant sync underlying data to upgrade tracker).gsheet"
    time.sleep(0.05)
    stub.touch()

    changed = w.check_for_changes()
    names = [e["name"] for e in changed]
    assert "DC CSE Tracker" in names


def test_only_changed_file_returned(watcher):
    """Only the modified file is in the changed list, not all files."""
    w, drive, inbox = watcher
    stub = drive / "EMEA Accounts CC Migrations.gsheet"
    time.sleep(0.05)
    stub.touch()

    changed = w.check_for_changes()
    assert len(changed) == 1
    assert changed[0]["name"] == "EMEA Accounts CC Migrations"


def test_mtime_updated_after_detection(watcher):
    """After detecting a change, the stored mtime is updated so it won't re-fire."""
    w, drive, inbox = watcher
    stub = drive / "EMEA Accounts CC Migrations.gsheet"
    time.sleep(0.05)
    stub.touch()

    w.check_for_changes()
    changed_again = w.check_for_changes()
    assert changed_again == []


def test_download_skipped_when_no_file_id(watcher):
    """download_and_stage returns None and logs warning when file_id is empty."""
    w, drive, inbox = watcher
    entry = {"name": "No ID File", "gsheet": "x.gsheet", "file_id": "", "priority": 5, "role": "secondary"}
    result = w.download_and_stage(entry)
    assert result is None


def test_export_url_format():
    """_export_url returns correct Google Sheets CSV export URL."""
    from agent.drive_watcher import _export_url
    url = _export_url("abc123")
    assert "abc123" in url
    assert "export" in url
    assert "format=csv" in url


def test_move_to_inbox(tmp_path, tmp_inbox):
    """_move_to_inbox moves file to inbox with timestamped name."""
    from agent.drive_watcher import _move_to_inbox
    src = tmp_path / "test_download.csv"
    src.write_text("a,b,c\n1,2,3")
    result = _move_to_inbox(src, tmp_inbox, "EMEA Accounts")
    assert result.exists()
    assert result.parent == tmp_inbox
    assert not src.exists()  # moved, not copied


def test_missing_gsheet_file_handled_gracefully(watcher):
    """Watcher doesn't crash when a .gsheet file doesn't exist on disk."""
    w, drive, inbox = watcher
    # Remove a file — simulates not-yet-synced state
    stub = drive / "EMEA Accounts CC Migrations.gsheet"
    stub.unlink()
    # Should not raise
    changed = w.check_for_changes()
    assert isinstance(changed, list)


def test_download_opens_browser_and_waits(watcher, tmp_path):
    """download_and_stage opens browser URL and moves downloaded CSV to inbox."""
    w, drive, inbox = watcher
    fake_csv = tmp_path / "fake_download.csv"
    fake_csv.write_text("id,name\n1,Acme")

    entry = {
        "name": "EMEA Accounts CC Migrations",
        "gsheet": "EMEA Accounts CC Migrations.gsheet",
        "file_id": "emea_fake_id_222",
        "priority": 2,
        "role": "primary",
    }

    with patch("agent.drive_watcher._open_in_browser"), \
         patch("agent.drive_watcher._wait_for_download", return_value=fake_csv):
        result = w.download_and_stage(entry)

    assert result is not None
    assert result.parent == inbox
    assert result.read_text().startswith("id,name")
