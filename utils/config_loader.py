"""Configuration loader and validator."""

import os
import yaml
from pathlib import Path
from typing import Any


def load_config(config_path: str = None) -> dict[str, Any]:
    """Load and validate config.yaml."""
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config.yaml"

    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Resolve env vars in string values
    config = _resolve_env_vars(config)

    # Ensure data directories exist
    project_root = Path(__file__).parent.parent
    for subdir in ["journals", "search_results", "pdfs", "extracted_text", "classifications"]:
        (project_root / "data" / subdir).mkdir(parents=True, exist_ok=True)
    (project_root / "output").mkdir(parents=True, exist_ok=True)
    (project_root / "logs").mkdir(parents=True, exist_ok=True)

    return config


def _resolve_env_vars(obj: Any) -> Any:
    """Recursively resolve ${ENV_VAR} patterns in string values."""
    if isinstance(obj, str):
        if obj.startswith("${") and obj.endswith("}"):
            return os.environ.get(obj[2:-1], obj)
        return obj
    elif isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve_env_vars(item) for item in obj]
    return obj
