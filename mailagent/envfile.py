"""Hilfsfunktionen zum Lesen und Schreiben der .env Datei."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from .config import ENV_PATH, ROOT


def ensure_env_file(path: Path = ENV_PATH) -> None:
    if not path.exists():
        shutil.copy(ROOT / ".env.example", path)


def set_env_value(key: str, value: str, path: Path = ENV_PATH) -> None:
    """Setzt KEY=value in der .env Datei, alle anderen Zeilen bleiben unverändert."""
    ensure_env_file(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    new_line = f"{key}={value}"
    for i, line in enumerate(lines):
        if line.split("=", 1)[0].strip() == key and not line.lstrip().startswith("#"):
            lines[i] = new_line
            break
    else:
        lines.append(new_line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[key] = value


def ask_and_save(key: str, question: str) -> str:
    """Fragt nach einem Wert, falls er noch fehlt, und speichert ihn in der .env."""
    current = (os.getenv(key) or "").strip()
    if current:
        return current
    value = input(f"{question}\n> ").strip()
    if value:
        set_env_value(key, value)
    return value
