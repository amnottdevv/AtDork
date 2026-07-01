"""
Atdork - Configuration Loader
Loads settings from a YAML file, environment variables, or defaults.
"""

import os
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Default configuration (fallback if no file is found)
DEFAULT_CONFIG: Dict[str, Any] = {
    "max_results": 20,
    "region": "us-en",
    "safesearch": "moderate",
    "timelimit": None,
    "backend": "auto",
    "timeout": 10,
    "retries": 2,
    "delay": 0.0,
    "user_agent": None,
    "proxy": None,
    "proxy_file": None,
    "tor": False,
    "strict": False,
    "proxy_cooldown": 60,
    "max_failures": 3,
    "concurrency": 1,
    "max_fallback_failures": 3,
    "batch_separator": ";",
    "format": "txt",
    "no_snippet": False,
    "no_validate": False,
    "strict_filter": False,
    "no_fallback_backends": False,
    "no_verify": False,
    "output_dir": None,
    "output": None,
    "debug": False,
}


def _load_yaml(filepath: str) -> Optional[Dict[str, Any]]:
    """Safely load a YAML file and return a dictionary or None on failure."""
    try:
        import yaml
    except ImportError:
        logger.warning("PyYAML is not installed. Install it with 'pip install pyyaml' to use config files.")
        return None

    if not os.path.isfile(filepath):
        return None

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            return data
        logger.warning("Config file %s does not contain a valid dictionary.", filepath)
        return None
    except Exception as e:
        logger.warning("Failed to load config file %s: %s", filepath, e)
        return None


def _merge_with_env(config: Dict[str, Any]) -> Dict[str, Any]:
    """Override config values with environment variables (ATDORK_<KEY>)."""
    for key in config:
        env_var = f"ATDORK_{key.upper()}"
        env_val = os.environ.get(env_var)
        if env_val is not None:
            # Convert to appropriate type
            if isinstance(config[key], bool):
                config[key] = env_val.lower() in ("true", "1", "yes")
            elif isinstance(config[key], int):
                try:
                    config[key] = int(env_val)
                except ValueError:
                    pass
            elif isinstance(config[key], float):
                try:
                    config[key] = float(env_val)
                except ValueError:
                    pass
            else:
                config[key] = env_val
    return config


def load_config(filepath: Optional[str] = None) -> Dict[str, Any]:
    """
    Load configuration from a YAML file, environment variables, and defaults.

    Priority (lowest to highest):
        1. Hard-coded defaults
        2. YAML file (atdork.yaml in current directory or given path)
        3. Environment variables (ATDORK_<KEY>)

    Args:
        filepath: Path to YAML config file. If None, looks for 'atdork.yaml'
                  in the current working directory.

    Returns:
        Merged configuration dictionary.
    """
    config = DEFAULT_CONFIG.copy()

    # Try to load from YAML
    if filepath is None:
        filepath = os.path.join(os.getcwd(), "atdork.yaml")

    yaml_config = _load_yaml(filepath)
    if yaml_config:
        # Only update keys that exist in DEFAULT_CONFIG
        for k, v in yaml_config.items():
            if k in config:
                config[k] = v
            else:
                logger.debug("Ignoring unknown config key: %s", k)
        logger.info("Configuration loaded from %s", filepath)

    # Override with environment variables
    config = _merge_with_env(config)

    return config
