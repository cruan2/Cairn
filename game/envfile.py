"""Minimal .env loader — zero dependencies (no python-dotenv needed).

Reads KEY=VALUE lines from the project-root .env and puts them in os.environ, but never
overrides a variable already set in the real shell (real env wins). Handles comments, blank
lines, optional `export ` prefixes, and quoted values.
"""
from __future__ import annotations
import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_env(path: Path = ENV_PATH) -> dict[str, str]:
    if not path.exists():
        return {}
    loaded: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, val)  # real environment takes precedence
            loaded[key] = val
    return loaded
