#!/usr/bin/env python3
"""Shared config helpers for XCrystal scripts (model path, .env parsing)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parent


def parse_env_file(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key:
            out[key] = val
    return out


_ENV_FILE: Optional[Dict[str, str]] = None


def _env_file() -> Dict[str, str]:
    global _ENV_FILE
    if _ENV_FILE is None:
        _ENV_FILE = parse_env_file(ROOT / ".env")
    return _ENV_FILE


def cfg(name: str, default: str = "") -> str:
    """Real environment variables override .env next to this module."""
    if name in os.environ and os.environ[name] != "":
        return os.environ[name]
    return _env_file().get(name, default)


def get_model_path() -> str:
    """
    Resolve Laya model path:
      1. env LAYA_MODEL_PATH
      2. LAYA_MODEL_PATH in project-root .env
      3. fail with a clear message
    Accepts a local directory or a Hugging Face repo id (for laya.load).
    """
    path = cfg("LAYA_MODEL_PATH", "").strip()
    if path:
        return path
    raise SystemExit(
        "LAYA_MODEL_PATH is not set. Copy .env.example to .env and set "
        "LAYA_MODEL_PATH to a local model directory (e.g. /path/to/laya/multilingual) "
        "or a Hugging Face repo id, or export LAYA_MODEL_PATH in your environment."
    )


if __name__ == "__main__":
    print(get_model_path())
