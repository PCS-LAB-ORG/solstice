from unittest.mock import MagicMock
from pathlib import Path
from agent.watcher import CsvDropHandler

def test_csv_handler_calls_callback_on_csv_created(tmp_path):
    called_with = []
    handler = CsvDropHandler(callback=lambda p: called_with.append(p))
    event = MagicMock()
    event.is_directory = False
    event.src_path = str(tmp_path / "accounts.csv")
    handler.on_created(event)
    assert len(called_with) == 1
    assert called_with[0] == Path(event.src_path)

def test_csv_handler_ignores_non_csv_files(tmp_path):
    called_with = []
    handler = CsvDropHandler(callback=lambda p: called_with.append(p))
    event = MagicMock()
    event.is_directory = False
    event.src_path = str(tmp_path / "notes.txt")
    handler.on_created(event)
    assert len(called_with) == 0

def test_csv_handler_ignores_directory_events(tmp_path):
    called_with = []
    handler = CsvDropHandler(callback=lambda p: called_with.append(p))
    event = MagicMock()
    event.is_directory = True
    event.src_path = str(tmp_path / "subdir")
    handler.on_created(event)
    assert len(called_with) == 0

def test_csv_handler_triggers_on_modified(tmp_path):
    called_with = []
    handler = CsvDropHandler(callback=lambda p: called_with.append(p))
    event = MagicMock()
    event.is_directory = False
    event.src_path = str(tmp_path / "accounts.csv")
    handler.on_modified(event)
    assert len(called_with) == 1
