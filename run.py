#!/usr/bin/env python3
"""Entry point — run from Solstice/ directory: python3 run.py"""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=FutureWarning, module="google")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="urllib3")

sys.path.insert(0, str(Path(__file__).parent))

from agent.main import main

if __name__ == "__main__":
    main()
