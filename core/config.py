"""
Atdork - Configuration Loader (schema v2)
Loads settings from layered YAML files, environment variables, and defaults.

Layered discovery (lowest → highest precedence):
    1. Hard-coded defaults (DEFAULT_CONFIG / SECTION_DEFAULTS)
    2. Global file: ~/.config/atdork/config.yml (| .yaml / atdork.yml / atdork.yaml)
    3. Working-directory file: atdork.yaml | AtDork.yaml | atdork.yml
    4. Explicit file (--config PATH, or env ATDORK_CONFIG when PATH not given)
    5. Environment variables (ATDORK_<KEY>)
    6. CLI flags (applied by the argument parser via set_defaults)

Schema v2 adds nested sections while keeping every legacy flat key working:

    version: 2
    search:    {backend, fallback, max_results, region, ...}   # search knobs
    engines:   {serper: {type: api, api_key: ${SERPER_API_KEY}, qps: 1}, ...}
    profiles:  {resilient: [google, serper, brave]}
    resilience:{circuit_breaker: {...}, cooldown: ...}
    output:    {format, dir}

A file becomes "v2" when it declares `version: 2` or contains any section key.
v2 files are validated strictly (unknown keys raise ConfigError); legacy v1
files keep the old lenient behaviour (unknown keys are ignored).
"""

import copy
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Flat CLI-facing defaults ───────────────────────────────────────────────
# Every key here must be a known argparse dest (regression-tested by
# tests/test_config.py::test_default_config_keys_all_known_to_parser).
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
    # Package manager (Atdork-DB)
    "db_repo": None,        # path to the Atdork-DB checkout
    "db_repo_url": None,    # git URL used by 'atdork update' hint
    "package_dir": None,    # local package store (default ~/.atdork/packages)
}

# ── Nested sections (schema v2) ────────────────────────────────────────────
SECTION_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "search": {},       # search knobs + 'fallback' (explicit backend chain)
    "engines": {},      # name -> {type: api, api_key, qps, ...}
    "profiles": {},     # name -> [backend, ...] (named chains for --backend)
    "resilience": {},   # circuit_breaker / cooldown tuning for --resilient
    "output": {},       # format / dir (flattened onto the CLI-facing keys)
    "workflows": {},    # reserved: workflow definitions (fase 3)
}

# Keys accepted inside the `search:` section (subset of search-related knobs).
SEARCH_KEYS = {
    "max_results", "region", "safesearch", "timelimit", "backend", "fallback",
    "timeout", "retries", "delay", "user_agent", "proxy", "proxy_file", "tor",
    "strict", "proxy_cooldown", "max_failures", "concurrency",
    "batch_separator", "resilient", "adaptive_delay", "no_fallback_backends",
}

# Keys accepted inside the `output:` section.
OUTPUT_KEYS = {"format", "dir", "output_dir", "no_snippet"}

# Top-level keys allowed in a v2 file.
KNOWN_ROOT_KEYS = set(DEFAULT_CONFIG) | set(SECTION_DEFAULTS) | {"version"}

# Discovery candidates (first existing file wins per layer).
_CWD_CANDIDATES = ("atdork.yaml", "AtDork.yaml", "atdork.yml")
_GLOBAL_CANDIDATES = ("config.yml", "config.yaml", "atdork.yml", "atdork.yaml")

# Last configuration produced by load_config(); lets other modules (package
# manager, database dork loader, providers) read settings without re-running
# discovery.
_CURRENT: Dict[str, Any] = {}


class ConfigError(Exception):
    """Raised for invalid configuration (schema violations, missing env vars)."""


# ── ${ENV} interpolation ───────────────────────────────────────────────────
_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _interpolate(value: Any, path: str, source: str,
                 unresolved: List[Tuple[str, str]]) -> Any:
    """Recursively expand ${VAR} / ${VAR:-default} in strings.

    Unresolvable variables (no default) are recorded in `unresolved` as
    (path, var) and replaced with an empty string; callers decide whether
    that is a warning (generic keys) or an error (engines.*.api_key).
    """
    if isinstance(value, str):
        def repl(match: "re.Match[str]") -> str:
            var, default = match.group(1), match.group(2)
            env_val = os.environ.get(var)
            if env_val is not None:
                return env_val
            if default is not None:
                return default
            unresolved.append((path, var))
            return ""
        return _ENV_RE.sub(repl, value)
    if isinstance(value, dict):
        return {
            k: _interpolate(v, f"{path}.{k}" if path else str(k), source, unresolved)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [
            _interpolate(v, f"{path}[{i}]", source, unresolved)
            for i, v in enumerate(value)
        ]
    return value


# ── Validation ─────────────────────────────────────────────────────────────
def _require_dict(data: Dict[str, Any], key: str, source: str) -> Dict[str, Any]:
    value = data.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{source}: '{key}' must be a mapping, got {type(value).__name__}")
    return value


def _validate_layer(data: Dict[str, Any], source: str) -> None:
    """Validate one interpolated YAML layer. Raises ConfigError on problems."""
    if not isinstance(data, dict):
        raise ConfigError(f"{source}: top level must be a mapping")

    version = data.get("version")
    if version is not None:
        if version not in (1, 2):
            raise ConfigError(f"{source}: unsupported config version {version!r} (supported: 1, 2)")

    is_v2 = version == 2 or any(k in SECTION_DEFAULTS for k in data)

    if not is_v2:
        return  # legacy v1: unknown keys are ignored later, as before

    unknown = [k for k in data if k not in KNOWN_ROOT_KEYS]
    if unknown:
        raise ConfigError(
            f"{source}: unknown key(s): {', '.join(sorted(unknown))} "
            f"(known: {', '.join(sorted(KNOWN_ROOT_KEYS))})"
        )

    search = _require_dict(data, "search", source)
    bad = [k for k in search if k not in SEARCH_KEYS]
    if bad:
        raise ConfigError(
            f"{source}: unknown search key(s): {', '.join(sorted(bad))} "
            f"(known: {', '.join(sorted(SEARCH_KEYS))})"
        )

    engines = _require_dict(data, "engines", source)
    for name, spec in engines.items():
        if not isinstance(spec, dict):
            raise ConfigError(f"{source}: engines.{name} must be a mapping")
        if "api_key" in spec and spec["api_key"] is not None and not isinstance(spec["api_key"], str):
            raise ConfigError(f"{source}: engines.{name}.api_key must be a string")
        ptype = spec.get("type", "api")
        if ptype != "api":
            raise ConfigError(
                f"{source}: engines.{name}.type {ptype!r} is not supported (supported: api)"
            )

    profiles = _require_dict(data, "profiles", source)
    for name, chain in profiles.items():
        if not isinstance(chain, list) or not chain or not all(isinstance(b, str) and b for b in chain):
            raise ConfigError(
                f"{source}: profiles.{name} must be a non-empty list of engine names"
            )

    resilience = _require_dict(data, "resilience", source)
    cb = resilience.get("circuit_breaker")
    if cb is not None and not isinstance(cb, dict):
        raise ConfigError(f"{source}: resilience.circuit_breaker must be a mapping")

    output = _require_dict(data, "output", source)
    bad = [k for k in output if k not in OUTPUT_KEYS]
    if bad:
        raise ConfigError(
            f"{source}: unknown output key(s): {', '.join(sorted(bad))} "
            f"(known: {', '.join(sorted(OUTPUT_KEYS))})"
        )

    _require_dict(data, "workflows", source)  # reserved (fase 3), opaque for now


def _check_engine_env(layer: Dict[str, Any], source: str,
                      unresolved: List[Tuple[str, str]]) -> None:
    """engines.*.api_key referencing an unset environment variable = error."""
    engines = layer.get("engines")
    if not isinstance(engines, dict):
        return
    for path_, var in unresolved:
        parts = path_.split(".")
        if len(parts) >= 3 and parts[0] == "engines" and parts[-1] == "api_key":
            raise ConfigError(f"{source}: {path_}: environment '{var}' is not set")


# ── YAML loading ───────────────────────────────────────────────────────────
def _load_yaml(filepath: str) -> Optional[Dict[str, Any]]:
    """Load a YAML file into a dict; None when the file does not exist."""
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
    except Exception as exc:
        raise ConfigError(f"{filepath}: failed to parse YAML: {exc}") from exc

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{filepath}: top level must be a mapping, got {type(data).__name__}")
    return data


# ── Merge helpers ──────────────────────────────────────────────────────────
def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _discover_paths(filepath: Optional[str]) -> List[str]:
    """Layer order: global → CWD → explicit (first existing name per layer)."""
    paths: List[str] = []

    if filepath is None:
        filepath = os.environ.get("ATDORK_CONFIG") or None

    global_dir = os.path.join(os.path.expanduser("~"), ".config", "atdork")
    for name in _GLOBAL_CANDIDATES:
        candidate = os.path.join(global_dir, name)
        if os.path.isfile(candidate):
            paths.append(candidate)
            break

    for name in _CWD_CANDIDATES:
        candidate = os.path.join(os.getcwd(), name)
        if os.path.isfile(candidate):
            paths.append(candidate)
            break

    if filepath:
        paths.append(filepath)

    return paths


def _merge_with_env(config: Dict[str, Any]) -> Dict[str, Any]:
    """Override flat config values with environment variables (ATDORK_<KEY>).

    Dict/list values (nested sections) are never replaced by env strings.
    """
    for key in list(config):
        if isinstance(config[key], (dict, list)):
            continue
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


# ── Public API ─────────────────────────────────────────────────────────────
def get_setting(key: str, default: Optional[Any] = None) -> Optional[Any]:
    """
    Read a single config setting: env ATDORK_<KEY> first (scalar keys only),
    then the last loaded config, then the given default.
    """
    current = _CURRENT.get(key)
    if not isinstance(current, (dict, list)):
        env_val = os.environ.get(f"ATDORK_{key.upper()}")
        if env_val is not None:
            return env_val
    if key in _CURRENT:
        return _CURRENT[key]
    return default


def load_config(filepath: Optional[str] = None) -> Dict[str, Any]:
    """
    Load configuration from layered YAML files, environment variables, and defaults.

    Args:
        filepath: Explicit YAML path (CLI --config). When None, the env var
                  ATDORK_CONFIG is consulted; discovery then always layers
                  the global file, the working-directory file, and the
                  explicit path (lowest → highest precedence).

    Returns:
        Merged configuration: flat legacy keys (CLI-facing) plus the nested
        sections under their section names.

    Raises:
        ConfigError: invalid schema, unparseable YAML, or an engines.*.api_key
                     that references an unset environment variable.
    """
    merged: Dict[str, Any] = {}
    for path in _discover_paths(filepath):
        layer = _load_yaml(path)
        if layer is None:
            if filepath:
                logger.warning("Config file %s not found; skipping.", path)
            continue

        unresolved: List[Tuple[str, str]] = []
        layer = _interpolate(layer, "", path, unresolved)
        _validate_layer(layer, path)
        _check_engine_env(layer, path, unresolved)
        for path_, var in unresolved:
            logger.warning(
                "Config %s: environment '%s' is not set (used at '%s'); value left empty.",
                path, var, path_ or "<root>",
            )

        merged = _deep_merge(merged, layer)

    # ── Start from defaults, then apply the merged layers ────────────────
    config = DEFAULT_CONFIG.copy()
    sections: Dict[str, Any] = {
        name: copy.deepcopy(defaults) for name, defaults in SECTION_DEFAULTS.items()
    }

    for key, value in merged.items():
        if key in sections:
            if isinstance(value, dict):
                sections[key] = _deep_merge(sections[key], value)
        elif key in config:
            config[key] = value
        elif key == "version":
            config["version"] = value
        else:
            # Legacy v1 behaviour: silently ignore unknown keys.
            logger.debug("Ignoring unknown config key: %s", key)

    # `search:` section wins over legacy root keys / defaults.
    for key, value in sections["search"].items():
        if key in config:
            config[key] = value

    # `output:` section flattens onto CLI-facing keys (dir → output_dir).
    output_section = sections["output"]
    if "dir" in output_section:
        output_section.setdefault("output_dir", output_section["dir"])
    for key in ("format", "output_dir", "no_snippet"):
        if key in output_section:
            config[key] = output_section[key]

    # Environment overrides (flat, scalar keys only), then attach sections.
    config = _merge_with_env(config)
    config.update(sections)

    # Publish for get_setting() so downstream modules see the same config
    _CURRENT.clear()
    _CURRENT.update(config)

    return config
