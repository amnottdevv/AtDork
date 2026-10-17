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
    "workflows": {},    # workflow definitions (core/workflow.py)
    "plugins": {},      # plugin system: enabled/disabled/paths/options
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

# Keys accepted inside the `plugins:` section.
PLUGINS_KEYS = {"enabled", "disabled", "paths", "options", "sources"}

# Keys accepted inside one `plugins.sources.<name>` entry.
PLUGINS_SOURCE_KEYS = {"url", "ref", "index"}

_SOURCE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

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

    # Workflows: structural check only (deep step-by-step validation lives in
    # core/workflow.py, invoked by `atdork workflow validate|run` — importing
    # it here would create a config↔workflow import cycle).
    workflows = _require_dict(data, "workflows", source)
    for wf_name, wf_def in workflows.items():
        if not isinstance(wf_def, dict):
            raise ConfigError(
                f"{source}: workflows.{wf_name} must be a mapping "
                f"with a 'steps:' list"
            )
        steps = wf_def.get("steps")
        if steps is not None and not isinstance(steps, list):
            raise ConfigError(
                f"{source}: workflows.{wf_name}.steps must be a list"
            )

    # Plugin system: enabled/disabled/paths/options — structural checks only
    # (the contract itself is validated by core/plugins.py at registration).
    plugins = _require_dict(data, "plugins", source)
    bad = [k for k in plugins if k not in PLUGINS_KEYS]
    if bad:
        raise ConfigError(
            f"{source}: unknown plugins key(s): {', '.join(sorted(bad))} "
            f"(known: {', '.join(sorted(PLUGINS_KEYS))})"
        )
    enabled = plugins.get("enabled")
    if enabled is not None and not (
            enabled == "auto"
            or (isinstance(enabled, list)
                and all(isinstance(n, str) for n in enabled))):
        raise ConfigError(
            f"{source}: plugins.enabled must be 'auto' or a list of plugin names"
        )
    for list_key in ("disabled", "paths"):
        value = plugins.get(list_key)
        if value is not None and not (
                isinstance(value, list)
                and all(isinstance(v, str) for v in value)):
            raise ConfigError(
                f"{source}: plugins.{list_key} must be a list of strings"
            )
    options = plugins.get("options")
    if options is not None:
        if not isinstance(options, dict):
            raise ConfigError(f"{source}: plugins.options must be a mapping")
        for opt_name, opt_values in options.items():
            if not isinstance(opt_values, dict):
                raise ConfigError(
                    f"{source}: plugins.options.{opt_name} must be a mapping "
                    f"of option defaults"
                )
    sources = plugins.get("sources")
    if sources is not None:
        if not isinstance(sources, dict):
            raise ConfigError(
                f"{source}: plugins.sources must be a mapping of source name "
                "to {url, ref?, index?}"
            )
        for src_name, spec in sources.items():
            where = f"plugins.sources.{src_name}"
            if not _SOURCE_NAME_RE.fullmatch(str(src_name)):
                raise ConfigError(
                    f"{source}: {where}: source names must match "
                    "^[A-Za-z0-9][A-Za-z0-9._-]*$"
                )
            if not isinstance(spec, dict):
                raise ConfigError(f"{source}: {where} must be a mapping")
            bad_spec = [k for k in spec if k not in PLUGINS_SOURCE_KEYS]
            if bad_spec:
                raise ConfigError(
                    f"{source}: {where}: unknown key(s): "
                    f"{', '.join(sorted(bad_spec))} "
                    f"(known: {', '.join(sorted(PLUGINS_SOURCE_KEYS))})"
                )
            url = spec.get("url")
            if not isinstance(url, str) or not url.strip():
                raise ConfigError(f"{source}: {where}.url must be a non-empty string")
            for key in ("ref", "index"):
                value = spec.get(key)
                if value is not None and (not isinstance(value, str) or not value.strip()):
                    raise ConfigError(
                        f"{source}: {where}.{key} must be a non-empty string"
                    )


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


def _discover_paths(filepath: Optional[str],
                    env_config_path: Optional[str] = None) -> List[str]:
    """Layer order: global → CWD → env config → explicit (first match per layer).

    When `env_config_path` is set (an environment is active) the working
    directory layer is skipped: config is deterministic and workspace-scoped,
    no accidental atdork.yaml from whatever folder you happen to be in.
    """
    paths: List[str] = []

    if filepath is None:
        filepath = os.environ.get("ATDORK_CONFIG") or None

    global_dir = os.path.join(os.path.expanduser("~"), ".config", "atdork")
    for name in _GLOBAL_CANDIDATES:
        candidate = os.path.join(global_dir, name)
        if os.path.isfile(candidate):
            paths.append(candidate)
            break

    if env_config_path is None:
        for name in _CWD_CANDIDATES:
            candidate = os.path.join(os.getcwd(), name)
            if os.path.isfile(candidate):
                paths.append(candidate)
                break

    if env_config_path:
        paths.append(env_config_path)

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


def override_setting(key: str, value: Any) -> None:
    """
    Runtime override of a single setting in the loaded config.

    Used by the environment (workspace) layer to redirect path-ish settings
    (package_dir, db_repo, ...) so downstream modules reading via
    get_setting() see the env-owned locations. Call after load_config().
    """
    _CURRENT[key] = value


def load_config(filepath: Optional[str] = None,
                env_config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load configuration from layered YAML files, environment variables, and defaults.

    Args:
        filepath: Explicit YAML path (CLI --config). When None, the env var
                  ATDORK_CONFIG is consulted; discovery then always layers
                  the global file, the working-directory file, and the
                  explicit path (lowest → highest precedence).
        env_config_path: Env-local config (``<env>/.config/config.yml``)
                  inserted above the working-directory layer. Passing it also
                  disables working-directory discovery (workspace-scoped).

    Returns:
        Merged configuration: flat legacy keys (CLI-facing) plus the nested
        sections under their section names.

    Raises:
        ConfigError: invalid schema, unparseable YAML, or an engines.*.api_key
                     that references an unset environment variable.
    """
    merged: Dict[str, Any] = {}
    for path in _discover_paths(filepath, env_config_path):
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

        # Section values override the SAME layer's root keys; flatten them
        # into the layer before merging so cross-layer precedence stays
        # natural (a higher layer's root key beats a lower layer's section).
        search_section = layer.get("search")
        if isinstance(search_section, dict):
            for key, value in search_section.items():
                if key in DEFAULT_CONFIG:
                    layer[key] = value
        out_section = layer.get("output")
        if isinstance(out_section, dict):
            for key in ("format", "output_dir", "no_snippet"):
                if key in out_section:
                    layer[key] = out_section[key]
            if "dir" in out_section and "output_dir" not in out_section:
                layer["output_dir"] = out_section["dir"]

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

    # Effective CLI-facing values already come out of the per-layer
    # flattening above (section keys were folded into each layer's root in
    # layer order). Sections stay stored under their names for modules
    # reading them via get_setting() (engines, profiles, search.fallback, ...).
    output_section = sections["output"]
    if "dir" in output_section:
        output_section.setdefault("output_dir", output_section["dir"])

    # Environment overrides (flat, scalar keys only), then attach sections.
    config = _merge_with_env(config)
    config.update(sections)

    # Publish for get_setting() so downstream modules see the same config
    _CURRENT.clear()
    _CURRENT.update(config)

    return config
