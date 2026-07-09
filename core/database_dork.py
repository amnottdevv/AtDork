"""
AtDork database dork loader (v1.3.9.5).

Loads dorks from the bundled GHDB database (`database/*.txt`) or from a
user-extracted copy. Supports:

- Listing available database files (with dork counts)
- Extracting the bundled database to a local directory
- Loading dorks by name (with/without .txt extension, with subdirectory paths)
- Combining multiple files via comma
- Random selection (--database-r)

Usage example (from atdork.py):

    from core.database_dork import (
        load_database_dorks,
        list_database_dorks,
        extract_database,
    )

    dorks = load_database_dorks("01_footholds,03_sensitive_directories",
                                random_count=10)
"""

from __future__ import annotations

import logging
import os
import random
import shutil
from importlib import resources
from importlib.resources.abc import Traversable
from typing import Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

DEFAULT_DATABASE_DIRNAME = "database"
DEFAULT_EXTRACT_DIRNAME = "database"  # extracted to ./database in CWD
VALID_EXTENSIONS = (".txt",)
COMMENT_PREFIXES = ("#", "//")

# Files to skip when listing/extracting (not dork files)
NON_DORK_FILES = {"readme.md", "readme.txt", "readme"}


# --------------------------------------------------------------------------- #
# Path resolution
# --------------------------------------------------------------------------- #

def _bundled_root() -> Optional[Traversable]:
    """
    Try to locate the bundled database via importlib.resources.

    Works only if `database/` is a Python package (i.e. has __init__.py).
    Returns the Traversable root or None.
    """
    # Common package names that might host the database
    for pkg in ("database", "atdork.database"):
        try:
            root = resources.files(pkg)
            # `resources.files()` returns the package itself; if it has any
            # children we treat it as a valid directory.
            try:
                _ = list(root.iterdir())
                return root
            except (NotADirectoryError, FileNotFoundError):
                continue
        except (ModuleNotFoundError, AttributeError):
            continue
    return None


def _filesystem_root() -> Optional[str]:
    """
    Find `database/` on the filesystem relative to this file or the CWD.

    Search order:
        1. ./database in CWD (extracted by --extract-database)
        2. ../database relative to core/ (repo root)
        3. database/ inside the atdork package directory
    """
    here = os.path.dirname(os.path.abspath(__file__))  # core/
    repo_root = os.path.dirname(here)                   # repo root
    candidates = [
        os.path.join(os.getcwd(), DEFAULT_DATABASE_DIRNAME),  # extracted
        os.path.join(repo_root, DEFAULT_DATABASE_DIRNAME),    # repo root
        os.path.join(here, DEFAULT_DATABASE_DIRNAME),         # core/database
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return None


def find_database_root(custom_path: Optional[str] = None) -> Union[str, Traversable]:
    """
    Resolve the database root directory.

    Resolution order:
      1. custom_path (if provided and exists)
      2. ./database in CWD (extracted by --extract-database)
      3. Bundled database/ alongside atdork.py (filesystem)
      4. Bundled database/ via importlib.resources (installed wheel)

    Args:
        custom_path: Optional override path.

    Returns:
        Either a str (filesystem path) or a Traversable (importlib.resources).

    Raises:
        FileNotFoundError: If no database directory can be found.
    """
    if custom_path:
        if not os.path.isdir(custom_path):
            raise FileNotFoundError(
                f"Database directory not found: '{custom_path}'. "
                "Run 'atdork --extract-database' first or specify a valid "
                "path with --database-path."
            )
        return custom_path

    # 1. Local ./database (extracted)
    local = os.path.join(os.getcwd(), DEFAULT_DATABASE_DIRNAME)
    if os.path.isdir(local):
        return local

    # 2. Bundled on filesystem
    fs_root = _filesystem_root()
    if fs_root:
        return fs_root

    # 3. Bundled via importlib.resources
    bundled = _bundled_root()
    if bundled is not None:
        return bundled

    raise FileNotFoundError(
        "Database directory not found. Run 'atdork --extract-database' to "
        "extract the bundled GHDB database to the current directory, or "
        "specify a path with --database-path."
    )


def _is_traversable(obj) -> bool:
    """True if obj is an importlib.resources Traversable (not a str)."""
    return hasattr(obj, "joinpath") and hasattr(obj, "iterdir") and not isinstance(obj, str)


# --------------------------------------------------------------------------- #
# Name normalization
# --------------------------------------------------------------------------- #

def _normalize_name(name: str) -> str:
    """
    Normalize a database dork spec into a relative path with .txt extension.

    Accepted forms:
        '01_footholds'           -> '01_footholds.txt'
        '01_footholds.txt'       -> '01_footholds.txt'
        '/db-1/1_none'           -> 'db-1/1_none.txt'
        '/db-1/1_none.txt'       -> 'db-1/1_none.txt'
        'db-1/1_none'            -> 'db-1/1_none.txt'
        'sub/dir/file'           -> 'sub/dir/file.txt'

    Rejects:
        - Empty names
        - Parent directory traversal ('..')
        - Absolute paths
        - Non-.txt extensions

    Args:
        name: Raw spec from the user.

    Returns:
        Normalized relative path with .txt extension.
    """
    name = name.strip()
    if not name:
        raise ValueError("Empty database dork name.")

    # Strip leading slashes (we want relative paths only)
    name = name.lstrip("/").lstrip("\\")

    # Reject absolute Windows paths (C:\...)
    if len(name) >= 2 and name[1] == ":":
        raise ValueError(f"Absolute paths not allowed: '{name}'")

    # Normalize separators
    name = name.replace("\\", "/")

    # Reject parent traversal
    parts = name.split("/")
    if ".." in parts:
        raise ValueError(
            f"Parent directory traversal ('..') is not allowed: '{name}'."
        )

    # Auto-append .txt if no extension
    _, ext = os.path.splitext(name)
    if not ext:
        name = name + ".txt"
    elif ext.lower() not in VALID_EXTENSIONS:
        raise ValueError(
            f"Unsupported extension '{ext}'. Only {VALID_EXTENSIONS} files "
            f"are supported (got '{name}')."
        )

    return name


# --------------------------------------------------------------------------- #
# Reading dorks
# --------------------------------------------------------------------------- #

def _parse_dork_lines(lines) -> List[str]:
    """
    Parse lines from a database file into a list of dorks.

    Skips:
        - Empty lines
        - Lines starting with '#' or '//' (comments)
    """
    dorks = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if any(line.startswith(p) for p in COMMENT_PREFIXES):
            continue
        dorks.append(line)
    return dorks


def _read_dorks_from_path(filepath: str) -> List[str]:
    """Read dorks from a filesystem path."""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        return _parse_dork_lines(f.readlines())


def _read_dorks_from_traversable(filepath: Traversable) -> List[str]:
    """Read dorks from an importlib.resources Traversable."""
    with filepath.open("r", encoding="utf-8", errors="replace") as f:
        return _parse_dork_lines(f.readlines())


# --------------------------------------------------------------------------- #
# Public API: load_database_dorks
# --------------------------------------------------------------------------- #

def load_database_dorks(
    spec: str,
    db_path: Optional[str] = None,
    random_count: Optional[int] = None,
    seed: Optional[int] = None,
) -> List[str]:
    """
    Load dorks from one or more database files.

    Args:
        spec: Comma-separated list of file specs. Each spec may be:
              - '01_footholds' or '01_footholds.txt' (file in database/ root)
              - '/db-1/1_none' or 'db-1/1_none' (subdirectory path)
              - 'subdir/file' (subdirectory path)
        db_path: Custom database root directory. If None, auto-discovered.
        random_count: If given, randomly select N dorks from the combined
            set (without replacement).
        seed: Optional random seed for reproducibility.

    Returns:
        List of dork query strings.

    Raises:
        FileNotFoundError: If a specified file or the database directory
            doesn't exist.
        ValueError: If a name has invalid format or random_count is invalid.
    """
    if not spec or not spec.strip():
        raise ValueError("Empty database dork spec.")

    root = find_database_root(db_path)

    # Parse comma-separated spec
    names = [n.strip() for n in spec.split(",") if n.strip()]
    if not names:
        raise ValueError("No database dork names provided.")

    all_dorks: List[str] = []
    loaded_files: List[str] = []

    for raw_name in names:
        rel_path = _normalize_name(raw_name)

        if _is_traversable(root):
            # Bundled via importlib.resources — walk the path components
            traversable = root
            for part in rel_path.split("/"):
                traversable = traversable.joinpath(part)
            if not traversable.is_file():
                raise FileNotFoundError(
                    f"Database dork file not found: '{rel_path}'. "
                    f"Use 'atdork --list-database-dork' to see available files."
                )
            dorks = _read_dorks_from_traversable(traversable)
        else:
            # Filesystem path
            full_path = os.path.join(root, rel_path)
            if not os.path.isfile(full_path):
                raise FileNotFoundError(
                    f"Database dork file not found: '{rel_path}'. "
                    f"Use 'atdork --list-database-dork' to see available files."
                )
            dorks = _read_dorks_from_path(full_path)

        loaded_files.append(rel_path)
        all_dorks.extend(dorks)
        logger.debug("Loaded %d dorks from '%s'", len(dorks), rel_path)

    # Deduplicate while preserving order
    seen = set()
    unique_dorks: List[str] = []
    for d in all_dorks:
        if d not in seen:
            seen.add(d)
            unique_dorks.append(d)
    if len(unique_dorks) < len(all_dorks):
        logger.debug(
            "Deduplication removed %d duplicate dorks across files.",
            len(all_dorks) - len(unique_dorks),
        )

    # Random selection (without replacement)
    if random_count is not None:
        if random_count <= 0:
            raise ValueError(
                f"--database-r must be > 0, got {random_count}."
            )
        if random_count > len(unique_dorks):
            logger.warning(
                "--database-r %d exceeds total dorks %d; using all dorks.",
                random_count, len(unique_dorks),
            )
            selected = list(unique_dorks)
        else:
            rng = random.Random(seed) if seed is not None else random.Random()
            selected = rng.sample(unique_dorks, random_count)
    else:
        selected = list(unique_dorks)

    logger.info(
        "Database dorks loaded: %d from %d file(s): %s",
        len(selected), len(loaded_files), ", ".join(loaded_files),
    )
    return selected


# --------------------------------------------------------------------------- #
# Public API: list_database_dorks
# --------------------------------------------------------------------------- #

def _is_dork_file(filename: str) -> bool:
    """True if filename is a candidate dork file (skip README etc)."""
    if not filename.lower().endswith(VALID_EXTENSIONS):
        return False
    base = os.path.splitext(filename.lower())[0]
    if base in NON_DORK_FILES:
        return False
    return True


def list_database_dorks(db_path: Optional[str] = None) -> List[Dict]:
    """
    List all available database dork files with their dork counts.

    Args:
        db_path: Custom database root directory. If None, auto-discovered.

    Returns:
        List of dicts with keys:
            - name: filename (e.g. '01_footholds.txt')
            - relpath: relative path from db root (e.g. '01_footholds.txt'
              or 'subdir/file.txt')
            - count: number of valid dork lines
            - size_bytes: file size in bytes (0 if unknown)
    """
    root = find_database_root(db_path)
    results: List[Dict] = []

    if _is_traversable(root):
        def walk_t(t: Traversable, prefix: str = "") -> None:
            for entry in sorted(t.iterdir(), key=lambda e: e.name):
                name = entry.name
                if entry.is_dir():
                    walk_t(entry, prefix + name + "/")
                elif entry.is_file():
                    if not _is_dork_file(name):
                        continue
                    rel = prefix + name
                    try:
                        dorks = _read_dorks_from_traversable(entry)
                        results.append({
                            "name": name,
                            "relpath": rel,
                            "count": len(dorks),
                            "size_bytes": 0,
                        })
                    except Exception as exc:
                        logger.warning("Failed to read %s: %s", rel, exc)
                        results.append({
                            "name": name,
                            "relpath": rel,
                            "count": 0,
                            "size_bytes": 0,
                        })
        walk_t(root)
    else:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()  # deterministic walk
            for fname in sorted(filenames):
                if not _is_dork_file(fname):
                    continue
                full = os.path.join(dirpath, fname)
                rel = os.path.relpath(full, root).replace(os.sep, "/")
                try:
                    dorks = _read_dorks_from_path(full)
                    results.append({
                        "name": fname,
                        "relpath": rel,
                        "count": len(dorks),
                        "size_bytes": os.path.getsize(full),
                    })
                except Exception as exc:
                    logger.warning("Failed to read %s: %s", rel, exc)
                    results.append({
                        "name": fname,
                        "relpath": rel,
                        "count": 0,
                        "size_bytes": 0,
                    })

    results.sort(key=lambda r: r["relpath"])
    return results


# --------------------------------------------------------------------------- #
# Public API: extract_database
# --------------------------------------------------------------------------- #

def extract_database(
    dest_dir: Optional[str] = None,
    overwrite: bool = False,
) -> str:
    """
    Extract the bundled database to a local directory.

    Args:
        dest_dir: Destination directory. Defaults to ./database in CWD.
        overwrite: If True, replace existing destination directory.

    Returns:
        Absolute path to the extracted directory.

    Raises:
        FileNotFoundError: If no bundled database can be found.
        FileExistsError: If dest_dir exists and overwrite is False.
    """
    if dest_dir is None:
        dest_dir = os.path.join(os.getcwd(), DEFAULT_EXTRACT_DIRNAME)
    dest_dir = os.path.abspath(dest_dir)

    # Locate source — prefer filesystem (faster + simpler), fall back to Traversable
    source_fs = _filesystem_root()
    source_t = _bundled_root() if source_fs is None else None

    if source_fs is None and source_t is None:
        raise FileNotFoundError(
            "Bundled database not found. Reinstall atdork or clone the "
            "repository so the `database/` folder is available."
        )

    # Reject extracting onto the source itself
    if source_fs is not None and os.path.abspath(source_fs) == dest_dir:
        raise ValueError(
            f"Destination '{dest_dir}' is the same as the bundled source. "
            "Choose a different destination with --extract-database-to."
        )

    # Handle existing destination
    if os.path.exists(dest_dir):
        if not overwrite:
            raise FileExistsError(
                f"Destination already exists: '{dest_dir}'. "
                "Use overwrite=True (or pass --force) to replace."
            )
        shutil.rmtree(dest_dir)

    os.makedirs(dest_dir, exist_ok=True)

    if source_fs is not None:
        # Filesystem → filesystem: use shutil.copytree into dest
        # (We've already created dest_dir, so copy each child instead)
        for entry in os.listdir(source_fs):
            src = os.path.join(source_fs, entry)
            dst = os.path.join(dest_dir, entry)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
    else:
        # Traversable → filesystem
        def copy_t(t: Traversable, prefix: str = "") -> None:
            for entry in t.iterdir():
                name = entry.name
                if entry.is_dir():
                    sub = os.path.join(dest_dir, prefix + name)
                    os.makedirs(sub, exist_ok=True)
                    copy_t(entry, prefix + name + os.sep)
                elif entry.is_file():
                    dst_file = os.path.join(dest_dir, prefix + name)
                    os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                    with entry.open("rb") as src, open(dst_file, "wb") as dst:
                        dst.write(src.read())
        copy_t(source_t)  # type: ignore[arg-type]

    return dest_dir
