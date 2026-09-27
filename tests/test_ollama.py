#!/usr/bin/env python3
"""
Live check that the local Ollama server is up and can generate with the bot's model.
Exits non-zero on failure.
"""
import os
import sys

import requests

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:0.6b")


def check_connection():
    response = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
    assert response.status_code == 200, f"/api/tags returned {response.status_code}"
    models = {m.get("name") for m in response.json().get("models", [])}
    assert OLLAMA_MODEL in models, f"model {OLLAMA_MODEL} not pulled (have: {sorted(models)})"
    print(f"✅ Ollama is running and {OLLAMA_MODEL} is available")


def check_generation():
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": "Hello! Can you respond with a simple greeting?",
        "stream": False,
        "think": False,
        "options": {"temperature": 0.7, "num_predict": 100},
    }
    response = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=60)
    response.raise_for_status()
    text = (response.json().get("response") or "").strip()
    assert text, "empty response from Ollama"
    print(f"✅ Generated: {text[:100]}")


def main() -> bool:
    print(f"Testing Ollama at {OLLAMA_HOST}...")
    for check in (check_connection, check_generation):
        try:
            check()
        except (AssertionError, requests.RequestException, ValueError) as error:
            print(f"❌ {check.__name__} failed: {error}")
            return False
    print("✅ All Ollama checks passed")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
