import logging
import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)

_DEBOUNCE_S = 5  # seconds — ignore repeat events for the same file within this window


class CsvDropHandler(FileSystemEventHandler):
    """Calls callback(path) when a CSV file is created or modified in the watched directory.
    Debounced: the same file is processed at most once per _DEBOUNCE_S seconds."""

    def __init__(self, callback: Callable[[Path], None]):
        super().__init__()
        self._callback = callback
        self._last_processed: dict[str, float] = {}

    def _handle(self, event) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() != ".csv":
            return
        now = time.monotonic()
        last = self._last_processed.get(str(path), 0)
        if now - last < _DEBOUNCE_S:
            logger.debug("Debounced duplicate event for %s", path.name)
            return
        self._last_processed[str(path)] = now
        logger.info("CSV detected: %s", path)
        self._callback(path)

    def on_created(self, event) -> None:
        self._handle(event)

    def on_modified(self, event) -> None:
        self._handle(event)


def start_watching(watch_dir: Path, callback: Callable[[Path], None]) -> None:
    """Start blocking watchdog loop. Ctrl+C to stop."""
    handler = CsvDropHandler(callback=callback)
    observer = Observer()
    observer.schedule(handler, str(watch_dir), recursive=False)
    observer.start()
    logger.info("Watching %s for CSV drops...", watch_dir)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
