"""Secrets and settings: environment variable first, then backend/.env (git-ignored)."""
import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def env_value(name: str, env_file: Path | None = None) -> str | None:
    value = os.environ.get(name)
    path = env_file or ENV_FILE
    if not value and path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, _, raw = line.partition("=")
            if key.strip() == name:
                value = raw.strip().strip('"').strip("'")
    return value or None
