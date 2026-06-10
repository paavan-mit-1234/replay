"""CLI local config: a small JSON file holding the token and active org."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

_CONFIG_DIR = Path.home() / ".replay"
_CONFIG_PATH = _CONFIG_DIR / "config.json"


@dataclass
class CliConfig:
    token: str | None = None
    org_id: str | None = None
    api_url: str = "http://localhost:8000"


def load() -> CliConfig:
    if _CONFIG_PATH.exists():
        data = json.loads(_CONFIG_PATH.read_text())
        return CliConfig(**{k: data.get(k) for k in CliConfig().__dict__})
    return CliConfig()


def save(config: CliConfig) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(asdict(config), indent=2))


def clear() -> None:
    if _CONFIG_PATH.exists():
        _CONFIG_PATH.unlink()
