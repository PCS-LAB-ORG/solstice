"""
llm.py — Local Ollama LLM wrapper for Solstice Agent.

No external APIs. All inference runs on local Ollama.

Usage:
    from agent.llm import ensure_ollama, chat

    ensure_ollama()          # call once at startup — starts Ollama if not running
    response = chat("...")   # returns text response
"""
from __future__ import annotations
import json
import logging
import subprocess
import time
import urllib.error
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

OLLAMA_BASE   = "http://localhost:11434"
PRIMARY_MODEL = "qwen2.5:14b"
FALLBACK_MODEL = "mistral-nemo:12b"
TIMEOUT_S     = 120  # Ollama can be slow on first load


def _is_running() -> bool:
    """Check if Ollama API is reachable."""
    try:
        urllib.request.urlopen(f"{OLLAMA_BASE}/api/tags", timeout=3)
        return True
    except Exception:
        return False


def ensure_ollama() -> None:
    """
    Ensure Ollama is running. If not, start it via `ollama serve`.
    Does NOT restart if already running.
    """
    if _is_running():
        logger.info("Ollama already running at %s", OLLAMA_BASE)
        return

    logger.info("Ollama not running — starting `ollama serve` in background...")
    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait up to 15s for it to become available
    for i in range(15):
        time.sleep(1)
        if _is_running():
            logger.info("Ollama started successfully (took %ds)", i + 1)
            return

    raise RuntimeError("Ollama failed to start within 15 seconds. Run `ollama serve` manually.")


def _best_model() -> str:
    """Return the best available model."""
    try:
        resp = urllib.request.urlopen(f"{OLLAMA_BASE}/api/tags", timeout=5)
        models = {m["name"] for m in json.loads(resp.read()).get("models", [])}
        if PRIMARY_MODEL in models:
            return PRIMARY_MODEL
        if FALLBACK_MODEL in models:
            logger.warning("Primary model %s not found, using %s", PRIMARY_MODEL, FALLBACK_MODEL)
            return FALLBACK_MODEL
        # Use whatever is available
        if models:
            m = next(iter(models))
            logger.warning("Using available model: %s", m)
            return m
    except Exception:
        pass
    return PRIMARY_MODEL


def chat(
    user_message: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    expect_json: bool = True,
) -> str:
    """
    Send a chat message to Ollama. Returns the response text.
    Raises RuntimeError if Ollama is not reachable.
    """
    if not _is_running():
        raise RuntimeError("Ollama is not running. Call ensure_ollama() first.")

    chosen_model = model or _best_model()
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model":    chosen_model,
        "messages": messages,
        "stream":   False,
    }
    if expect_json:
        payload["format"] = "json"

    body = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        f"{OLLAMA_BASE}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            data = json.loads(resp.read())
            return data["message"]["content"]
    except urllib.error.URLError as e:
        raise RuntimeError(f"Ollama request failed: {e}") from e
