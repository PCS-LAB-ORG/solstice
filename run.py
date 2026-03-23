#!/usr/bin/env python3
"""Entry point — run from Solstice/ directory: python3 run.py"""
import sys
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

    from agent.main import main
    main()
