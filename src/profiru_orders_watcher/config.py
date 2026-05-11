from __future__ import annotations

from pathlib import Path

import yaml

from profiru_orders_watcher.models import AppConfig


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    return AppConfig.model_validate(data)
