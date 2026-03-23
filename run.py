#!/usr/bin/env python3
"""Entry point — run from Solstice/ directory: python3 run.py"""
import sys
import threading
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agent.llm import ensure_ollama

if __name__ == "__main__":
    # Ensure Ollama is running before starting the agent — starts it if needed, never restarts
    print("Checking Ollama...")
    try:
        ensure_ollama()
        print("✓ Ollama ready")
    except RuntimeError as e:
        print(f"✗ {e}")
        sys.exit(1)

    from agent.main import main, run_pipeline
    from agent.constants import INBOX_DIR
    from agent.drive_watcher import DriveFileWatcher

    # Start Google Drive watcher in background thread
    # Monitors .gsheet mtimes → triggers browser download → moves to data/inbox/
    def start_drive_watcher():
        try:
            watcher = DriveFileWatcher(inbox=INBOX_DIR)
            watcher.print_config_status() if hasattr(watcher, 'print_config_status') else None
            watcher.run(pipeline_callback=run_pipeline)
        except Exception as e:
            import logging
            logging.getLogger("drive_watcher").error("Drive watcher failed: %s", e)

    from agent.drive_watcher import print_config_status
    print_config_status()

    drive_thread = threading.Thread(target=start_drive_watcher, daemon=True, name="drive-watcher")
    drive_thread.start()
    print("✓ Drive watcher running (60s poll)")

    main()
