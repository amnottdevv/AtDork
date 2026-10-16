"""
Atdork - Environment (workspace) support (core/env.py)

An *environment* is a single folder root that becomes AtDork's entire world:
every file AtDork writes (results, logs, cache, resume/database state,
package store, cloned Atdork-DB, env-local config) lives inside that root and
never outside it. Environments are marked by a `.atdork-env` marker file, so
they are portable — copy the folder and the whole state moves with it.

Layout created by `atdork env create`:

    <root>/
    ├── .atdork-env              # marker (version, name, created_at)
    ├── .config/
    │   ├── config.yml           # env-local config layer
    │   └── packages/            # package store + Atdork-DB clone
    ├── cache/                   # cache database
    ├── results/                 # dork results
    ├── logs/                    # log files
    ├── state/                   # resume/dedup SQLite + session state
    └── tmp/

Resolution precedence (first hit wins):

    1. --env /path            (CLI flag)
    2. ATDORK_ENV=/path       (environment variable)
    3. registry active env    (set by `atdork env use`, ~/.config/atdork/environments.yml)

Strict path guard: `Env.guard_write()` resolves a path (symlink-safe) and
raises `EnvEscapeError` unless the result stays inside the environment root.
This is isolation, not encryption — files inside the root are plaintext.
"""

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MARKER_NAME = ".atdork-env"
MARKER_VERSION = 1

# Directories created inside every environment (relative to root).
LAYOUT_DIRS = (
    ".config",
    os.path.join(".config", "packages"),
    "cache",
    "results",
    "logs",
    "state",
    "tmp",
)

# Registry of known/active environments (written by `atdork env use`).
REGISTRY_FILENAME = "environments.yml"


class EnvError(Exception):
    """Environment resolution/creation problem (bad root, missing marker)."""


class EnvEscapeError(EnvError):
    """A write path resolved outside the environment root."""


# ── Registry ───────────────────────────────────────────────────────────────

def registry_path() -> Path:
    return Path.home() / ".config" / "atdork" / REGISTRY_FILENAME


def read_registry() -> Dict[str, Any]:
    """{active: str|None, known: [str, ...]} — tolerant of missing file."""
    path = registry_path()
    if not path.is_file():
        return {"active": None, "known": []}
    try:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # corrupt registry must not break the CLI
        logger.warning("Could not read environment registry %s: %s", path, exc)
        return {"active": None, "known": []}
    active = data.get("active")
    known = data.get("known") or []
    return {
        "active": str(active) if active else None,
        "known": [str(k) for k in known if k],
    }


def write_registry(data: Dict[str, Any]) -> None:
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    import yaml
    path.write_text(
        yaml.safe_dump(
            {"active": data.get("active"), "known": data.get("known") or []},
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def register_env(root: Path) -> None:
    reg = read_registry()
    root_s = str(root)
    if root_s not in reg["known"]:
        reg["known"].append(root_s)
        write_registry(reg)


def unregister_env(root: Path) -> None:
    reg = read_registry()
    root_s = str(root)
    reg["known"] = [k for k in reg["known"] if k != root_s]
    if reg["active"] == root_s:
        reg["active"] = None
    write_registry(reg)


def set_active_env(root: Optional[Path]) -> None:
    reg = read_registry()
    reg["active"] = str(root) if root else None
    write_registry(reg)


def list_env_roots() -> List[str]:
    return read_registry()["known"]


# ── Env class ──────────────────────────────────────────────────────────────

class Env:
    """A resolved AtDork environment rooted at a folder with a marker file."""

    def __init__(self, root: Path, meta: Optional[Dict[str, Any]] = None):
        self.root = Path(root).expanduser().resolve()
        self.meta = meta or {}

    # ── Identity ───────────────────────────────────────────────────────
    @property
    def marker_file(self) -> Path:
        return self.root / MARKER_NAME

    @property
    def name(self) -> Optional[str]:
        return self.meta.get("name")

    @classmethod
    def at(cls, path) -> Optional["Env"]:
        """Return an Env for `path` when it holds a marker, else None."""
        root = Path(path).expanduser()
        marker = root / MARKER_NAME
        if not marker.is_file():
            return None
        meta: Dict[str, Any] = {}
        try:
            meta = json.loads(marker.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            logger.warning("Unreadable env marker %s: %s", marker, exc)
        return cls(root, meta)

    # ── Layout ─────────────────────────────────────────────────────────
    @property
    def config_file(self) -> Path:
        return self.root / ".config" / "config.yml"

    @property
    def packages_dir(self) -> Path:
        return self.root / ".config" / "packages"

    @property
    def db_repo(self) -> Path:
        return self.packages_dir / "Atdork-DB"

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @property
    def cache_db(self) -> Path:
        return self.cache_dir / "atdork_cache.db"

    @property
    def results_dir(self) -> Path:
        return self.root / "results"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def log_file(self) -> Path:
        return self.logs_dir / "atdork.log"

    @property
    def state_dir(self) -> Path:
        return self.root / "state"

    @property
    def db_path(self) -> Path:
        return self.state_dir / "atdork.db"

    @property
    def tmp_dir(self) -> Path:
        return self.root / "tmp"

    def ensure_layout(self) -> None:
        for rel in LAYOUT_DIRS:
            (self.root / rel).mkdir(parents=True, exist_ok=True)

    # ── Strict path guard ──────────────────────────────────────────────
    def guard_write(self, path) -> Path:
        """Resolve `path` and require it to stay inside the environment.

        Relative paths resolve against the **environment root** (an active
        environment is the working world — ``results/x.json`` means
        ``<root>/results/x.json``); absolute paths are used as-is. Symlinks
        and ``..`` are followed before the containment check, so a path can
        never sneak out of the root.
        """
        target = Path(path).expanduser()
        if not target.is_absolute():
            target = self.root / target
        try:
            resolved = target.resolve()
        except OSError as exc:
            raise EnvError(f"Cannot resolve path '{path}': {exc}") from exc
        if resolved != self.root and self.root not in resolved.parents:
            raise EnvEscapeError(
                f"'{path}' resolves to '{resolved}' which is outside the "
                f"environment '{self.root}'. While an environment is active, "
                f"all written files must stay inside it — pick a path under "
                f"the root, or run without --env/ATDORK_ENV."
            )
        return resolved

    # ── Info ───────────────────────────────────────────────────────────
    def describe_paths(self) -> Dict[str, str]:
        return {
            "root": str(self.root),
            "config": str(self.config_file),
            "packages": str(self.packages_dir),
            "db_repo": str(self.db_repo),
            "cache": str(self.cache_db),
            "results": str(self.results_dir),
            "log": str(self.log_file),
            "state": str(self.db_path),
        }

    def usage_bytes(self) -> Dict[str, int]:
        totals: Dict[str, int] = {}
        for rel in LAYOUT_DIRS:
            base = self.root / rel
            total = 0
            for dirpath, _dirnames, filenames in os.walk(base):
                for fn in filenames:
                    try:
                        total += os.path.getsize(os.path.join(dirpath, fn))
                    except OSError:
                        pass
            totals[rel] = total
        return totals


# ── Create / destroy ───────────────────────────────────────────────────────

def create_env(path, name: Optional[str] = None, force: bool = False) -> Env:
    """Create (idempotent) an environment rooted at `path`."""
    root = Path(path).expanduser()
    try:
        root.mkdir(parents=True, exist_ok=True)
        root = root.resolve()
    except OSError as exc:
        raise EnvError(f"Cannot create environment at '{path}': {exc}") from exc

    marker = root / MARKER_NAME
    if marker.is_file() and not force:
        env = Env.at(root)  # already an env — keep its marker, refresh layout
    else:
        meta = {
            "version": MARKER_VERSION,
            "name": name or root.name,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        marker.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        env = Env(root, meta)

    env.ensure_layout()
    register_env(root)
    return env


def destroy_env(root, delete_files: bool = False) -> None:
    """Unregister an environment; optionally delete its folder entirely."""
    env_path = Path(root).expanduser()
    env = Env.at(env_path)
    if env is None:
        raise EnvError(f"'{root}' is not an AtDork environment (no {MARKER_NAME}).")
    if delete_files:
        shutil.rmtree(env.root)
    else:
        env.marker_file.unlink(missing_ok=True)
    unregister_env(env.root)


# ── Resolution ─────────────────────────────────────────────────────────────

def resolve_env(cli_env: Optional[str] = None) -> Optional[Env]:
    """Resolve the active environment (flag > ATDORK_ENV > registry).

    Explicit sources (`--env`, ATDORK_ENV) raise EnvError when the path is
    not a valid environment; a stale registry entry only warns and returns
    None, so plain searches keep working.
    """
    if cli_env:
        return _require_env(cli_env, source="--env")
    env_var = os.environ.get("ATDORK_ENV")
    if env_var:
        return _require_env(env_var, source="ATDORK_ENV")
    active = read_registry().get("active")
    if active:
        env = Env.at(active)
        if env is None:
            logger.warning(
                "Registered environment '%s' no longer exists; ignoring. "
                "Set another with 'atdork env use <path>'.", active,
            )
        return env
    return None


def _require_env(path: str, source: str) -> Env:
    env = Env.at(path)
    if env is None:
        raise EnvError(
            f"{source}: '{path}' is not an AtDork environment "
            f"(missing {MARKER_NAME}). Create it first: atdork env create {path}"
        )
    return env


def guard_if_env(path, cli_env: Optional[str] = None):
    """Constrain an explicit write path to the environment when one is active."""
    if path is None:
        return None
    env = resolve_env(cli_env)
    if env is None:
        return path
    return str(env.guard_write(path))
