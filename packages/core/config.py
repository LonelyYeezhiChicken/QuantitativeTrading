"""Core Domain & Configuration Package."""

from pathlib import Path
import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent.parent

def load_config(config_path: str = "config/config.yaml") -> dict:
    """Load yaml configuration safely."""
    path = ROOT_DIR / config_path
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
