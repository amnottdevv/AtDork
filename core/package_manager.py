"""
Atdork Package Manager (core/package_manager.py)

Manages dork packages sourced from the Atdork-DB repository
(https://github.com/amnottdevv/Atdork-DB).

The repository layout is one folder per theme plus a manifest:

    Atdork-DB/
    ├── Index.idn          # manifest: ref|sha256|bytes|dork-lines|description
    ├── @cve/cve_1.txt
    ├── @exploit-db/Footholds.txt
    └── ...

Reference grammar (accepted anywhere a package ref is needed):

    @cve/cve_1.txt      canonical reference (folder + file)
    c@cve_1.txt         shorthand — 'c' resolves to the unique folder
                        starting with 'c' that contains 'cve_1.txt'
    cve_1.txt           bare file name (must be unique in the index)
    @cve                whole folder (install/uninstall only)

Resolution order for an installed copy: local package store first
(~/.atdork/packages by default), then the Atdork-DB checkout itself.
"""

from __future__ import annotations

import difflib
import hashlib
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

INDEX_NAME = "Index.idn"
INDEX_HEADER = "Atdork-DB index"
DB_REPO_NAME = "Atdork-DB"
DB_REPO_URL = "https://github.com/amnottdevv/Atdork-DB.git"
# Plugin tools live under this folder (optionally in tool subfolders) and
# are Python modules, not dork content.
PLUGIN_FOLDER = "@plugins"
# Every data file in the repo is installable/searchable; loading files as
# queries (.txt line-per-dork) is enforced separately by core.database_dork.
# .py entries are plugin modules (@plugins/<tool>/...): installable and
# searchable, but never loaded as dork content.
VALID_EXTS = (".txt", ".csv", ".json", ".py")
INDEX_FIELD_SEPARATOR = "|"


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #

class PackageError(Exception):
    """Base class for package manager errors."""


class DBRepoNotFound(PackageError):
    """The Atdork-DB repository could not be located."""


class IndexNotFound(PackageError):
    """The repository was found but Index.idn is missing."""


class RefError(PackageError):
    """A package reference could not be understood or resolved."""

    def __init__(self, message: str, suggestions: Optional[Sequence[str]] = None):
        super().__init__(message)
        self.suggestions: List[str] = list(suggestions or [])


class RefNotFound(RefError):
    """No package in the index matches the reference."""


class AmbiguousRef(RefError):
    """The reference matches more than one package."""


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class IndexEntry:
    """One line of Index.idn: a single installable dork file."""

    folder: str
    name: str
    sha256: str
    size_bytes: int
    dork_lines: int
    description: str = ""

    @property
    def ref(self) -> str:
        return f"@{self.folder}/{self.name}"

    @property
    def relpath(self) -> str:
        return f"{self.folder}/{self.name}"


@dataclass(frozen=True)
class Ref:
    """Parsed package reference."""

    folder: Optional[str]   # folder name or prefix, None if not given
    name: Optional[str]     # file name, None for folder-wide refs
    exact_folder: bool      # True when written as @folder/file


@dataclass(frozen=True)
class InstallOutcome:
    """Result of installing one reference (file or folder)."""

    entry: IndexEntry
    path: Path
    status: str             # "installed" | "updated" | "exists"


@dataclass(frozen=True)
class InstalledPackage:
    """An entry present in the local package store."""

    folder: str
    name: str
    path: Path
    size_bytes: int
    dork_lines: int
    status: str             # "ok" | "modified" | "orphan"


# --------------------------------------------------------------------------- #
# Configuration helpers
# --------------------------------------------------------------------------- #

def _cfg(key: str) -> Optional[str]:
    """Read a package-manager setting: env var first, then loaded config."""
    try:
        from core.config import get_setting
        return get_setting(key)
    except Exception:  # pragma: no cover - config module always available
        return None


def _as_path(value) -> Path:
    return Path(os.path.expanduser(str(value))).resolve()


def get_package_dir(explicit: Optional[str] = None) -> Path:
    """Local package store directory (no mkdir side effects)."""
    if explicit:
        return _as_path(explicit)
    cfg_val = _cfg("package_dir")
    if cfg_val:
        return _as_path(cfg_val)
    return Path.home() / ".atdork" / "packages"


def find_db_repo(explicit: Optional[str] = None) -> Path:
    """Locate the Atdork-DB checkout or raise DBRepoNotFound."""
    repo = try_find_db_repo(explicit)
    if repo is None:
        looked = _search_paths(explicit)
        pretty = "\n  ".join(str(p) for p in looked)
        raise DBRepoNotFound(
            "Atdork-DB repository not found. Looked in:\n"
            f"  {pretty}\n"
            "Set it with --db-repo, config key 'db_repo', or env "
            "ATDORK_DB_REPO, or clone it:\n"
            f"  git clone {DB_REPO_URL}"
        )
    return repo


def _search_paths(explicit: Optional[str]) -> List[Path]:
    paths: List[Path] = []
    if explicit:
        paths.append(_as_path(explicit))
    cfg_val = _cfg("db_repo")
    if cfg_val:
        paths.append(_as_path(cfg_val))
    paths.append(Path.home() / DB_REPO_NAME)
    # Sibling of this checkout: <parent-of-atdork>/Atdork-DB
    paths.append(Path(__file__).resolve().parents[2] / DB_REPO_NAME)
    paths.append(Path.cwd() / DB_REPO_NAME)
    # de-duplicate, keep order
    seen, unique = set(), []
    for p in paths:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def try_find_db_repo(explicit: Optional[str] = None) -> Optional[Path]:
    """Like find_db_repo but returns None instead of raising."""
    for path in _search_paths(explicit):
        if path.is_dir():
            return path
    return None


# --------------------------------------------------------------------------- #
# Index
# --------------------------------------------------------------------------- #

def index_file(repo: Path) -> Path:
    return repo / INDEX_NAME


def load_index(repo: Optional[str] = None, config: Optional[Dict] = None) -> List[IndexEntry]:
    """
    Parse Index.idn from the Atdork-DB repository.

    Args:
        repo: Explicit repository path (overrides discovery).
        config: Optional config dict; accepted for call-site symmetry.

    Raises:
        DBRepoNotFound: Repository not found.
        IndexNotFound: Index.idn missing (needs 'atdork index --build').
    """
    root = find_db_repo(repo)
    path = index_file(root)
    if not path.is_file():
        raise IndexNotFound(
            f"{INDEX_NAME} not found in {root}. "
            "Run 'atdork index --build' (after changing data) or "
            f"'git -C {root} pull' to fetch it."
        )

    entries: List[IndexEntry] = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(INDEX_FIELD_SEPARATOR)
            if len(parts) < 4 or "/" not in parts[0]:
                logger.warning("%s:%d: malformed index line skipped", path.name, lineno)
                continue
            ref, sha, size, lines = parts[:4]
            description = parts[4] if len(parts) > 4 else ""
            folder, name = ref.lstrip("@").split("/", 1)
            if not folder or not name:
                logger.warning("%s:%d: malformed index line skipped", path.name, lineno)
                continue
            try:
                entries.append(IndexEntry(
                    folder=folder,
                    name=name,
                    sha256=sha.strip(),
                    size_bytes=int(size),
                    dork_lines=int(lines),
                    description=description,
                ))
            except ValueError:
                logger.warning("%s:%d: non-numeric size/lines skipped", path.name, lineno)
    return entries


def index_folders(entries: Iterable[IndexEntry]) -> List[str]:
    return sorted({e.folder for e in entries})


def read_index_header(repo: Optional[str] = None) -> Dict[str, str]:
    """Parse the '# key: value' header lines of Index.idn."""
    path = index_file(find_db_repo(repo))
    if not path.is_file():
        raise IndexNotFound(f"{INDEX_NAME} not found in {path.parent}. Run 'atdork index --build'.")
    header: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line.startswith("#"):
                break
            m = re.match(r"#\s*([a-z-]+):\s*(.*)$", line)
            if m:
                header[m.group(1)] = m.group(2)
    return header


# --------------------------------------------------------------------------- #
# Reference parsing & resolution
# --------------------------------------------------------------------------- #

_FOLDER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def parse_ref(raw: str) -> Ref:
    """
    Parse a package reference into (folder, name).

        '@cve/cve_1.txt'  -> Ref(folder='cve', name='cve_1.txt', exact=True)
        'c@cve_1.txt'     -> Ref(folder='c',   name='cve_1.txt', exact=False)
        '@cve'            -> Ref(folder='cve', name=None,        exact=True)
        'cve_1.txt'       -> Ref(folder=None,  name='cve_1.txt', exact=False)
    """
    raw = (raw or "").strip()
    if not raw:
        raise RefError("Empty package reference.")

    if raw.startswith("@"):
        rest = raw[1:]
        folder_part, _, name_part = rest.partition("/")
        if not _FOLDER_RE.fullmatch(folder_part or ""):
            raise RefError(
                f"Invalid reference '{raw}': '@' must be followed by a valid "
                "folder name (letters, digits, '.', '_', '-')."
            )
        return Ref(folder=folder_part, name=name_part or None, exact_folder=True)

    if "@" in raw:
        hint, _, name = raw.partition("@")
        if not _FOLDER_RE.fullmatch(hint or ""):
            raise RefError(
                f"Invalid reference '{raw}': '@' must be preceded by a valid "
                "folder prefix (letters, digits, '.', '_', '-')."
            )
        return Ref(folder=hint, name=name or None, exact_folder=False)

    # Bare reference: 'file.txt' or a legacy 'sub/file.txt' path.
    # The directory part is treated as a hint only via the file name.
    base = Path(raw.replace("\\", "/")).name
    return Ref(folder=None, name=base, exact_folder=False)


def _candidate_names(name: str) -> List[str]:
    """File names to try, preferring an auto-appended .txt (legacy style);
    bare names inside @plugins resolve to .py modules too."""
    _, ext = os.path.splitext(name)
    if ext:
        return [name]
    return [name + ".txt", name + ".py", name]


def _safe(name: str) -> bool:
    parts = name.replace("\\", "/").split("/")
    return ".." not in parts and not name.startswith("/") and "://" not in name


def resolve_entry(raw: str, index: Optional[List[IndexEntry]] = None,
                  config: Optional[Dict] = None) -> IndexEntry:
    """Resolve a file-level reference to an IndexEntry."""
    entries = index if index is not None else load_index(config=config)
    if not entries:
        raise RefNotFound("The index is empty. Run 'atdork index --build' inside Atdork-DB.")

    ref = parse_ref(raw)
    if ref.name is None:
        raise RefError(
            f"'{raw}' refers to a whole folder; add a file name "
            f"(e.g. '@{ref.folder}/...') or use install/uninstall with the folder ref."
        )
    if not _safe(ref.name):
        raise RefError(f"Unsafe package reference: '{raw}'")

    names = _candidate_names(ref.name)

    # 1. Canonical @folder/file
    if ref.folder and ref.exact_folder:
        hits = [e for e in entries if e.folder == ref.folder and e.name in names]
        if len(hits) == 1:
            return hits[0]
        in_folder = sorted(e.name for e in entries if e.folder == ref.folder)
        if not in_folder:
            raise RefNotFound(
                f"Folder '@{ref.folder}' is not in the index.",
                suggestions=[f"@{f}/" for f in index_folders(entries)],
            )
        close = difflib.get_close_matches(ref.name, in_folder, n=5, cutoff=0.5)
        raise RefNotFound(
            f"Package '{ref.name}' not found in '@{ref.folder}'.",
            suggestions=[f"@{ref.folder}/{m}" for m in close],
        )

    # 2. Shorthand c@file — unique folder prefix (file presence disambiguates)
    if ref.folder:
        hinted = sorted(f for f in index_folders(entries)
                        if f == ref.folder or f.startswith(ref.folder))
        exact = [e for e in entries if e.folder in hinted and e.name in names]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            raise AmbiguousRef(
                f"'{raw}' matches {len(exact)} packages.",
                suggestions=[e.ref for e in exact],
            )
        if not hinted:
            raise RefNotFound(
                f"No folder starts with '{ref.folder}'.",
                suggestions=[f"@{f}" for f in index_folders(entries)],
            )
        pool = [e for e in entries if e.folder in hinted]
        close = difflib.get_close_matches(ref.name, [e.name for e in pool], n=5, cutoff=0.5)
        if close:
            match = next(e for e in pool if e.name == close[0])
            raise RefNotFound(f"Package '{ref.name}' not found.", suggestions=[match.ref])
        raise RefNotFound(
            f"Package '{ref.name}' not found in folder(s): "
            + ", ".join(f"@{f}" for f in hinted),
        )

    # 3. Bare file name
    hits = [e for e in entries if e.name in names]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise AmbiguousRef(
            f"'{ref.name}' matches {len(hits)} packages.",
            suggestions=[e.ref for e in hits],
        )
    close = difflib.get_close_matches(ref.name, [e.name for e in entries], n=5, cutoff=0.6)
    raise RefNotFound(
        f"Package '{ref.name}' is not in the index.",
        suggestions=[e.ref for e in entries if e.name in close],
    )


def resolve_folder(raw: str, index: Optional[List[IndexEntry]] = None,
                   config: Optional[Dict] = None) -> str:
    """Resolve a folder-wide reference ('@cve' or 'c@') to a folder name."""
    entries = index if index is not None else load_index(config=config)
    ref = parse_ref(raw)
    if ref.folder is None:
        raise RefError(f"'{raw}' is not a folder reference (expected '@folder').")
    folders = index_folders(entries)
    exact = [f for f in folders if f == ref.folder]
    if exact:
        return exact[0]
    hinted = [f for f in folders if f.startswith(ref.folder)]
    if len(hinted) == 1:
        return hinted[0]
    if len(hinted) > 1:
        raise AmbiguousRef(
            f"'{ref.folder}' matches {len(hinted)} folders.",
            suggestions=[f"@{f}" for f in hinted],
        )
    close = difflib.get_close_matches(ref.folder, folders, n=5, cutoff=0.5)
    raise RefNotFound(
        f"Folder '{ref.folder}' is not in the index.",
        suggestions=[f"@{f}" for f in close],
    )


# --------------------------------------------------------------------------- #
# Paths & checksums
# --------------------------------------------------------------------------- #

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_dork_lines(path: Path) -> int:
    # Plugin modules (.py) are code, not dork content — never counted.
    if path.suffix.lower() == ".py":
        return 0
    count = 0
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                count += 1
    return count


def source_path(entry: IndexEntry, repo: Optional[str] = None,
                config: Optional[Dict] = None) -> Path:
    """Path of the package inside the Atdork-DB checkout (folder dir is '@name')."""
    root = find_db_repo(repo)
    return root / f"@{entry.folder}" / entry.name


def installed_path(entry: IndexEntry, package_dir: Optional[str] = None) -> Path:
    """Path of the package inside the local store."""
    return get_package_dir(package_dir) / entry.folder / entry.name


def is_installed(entry: IndexEntry, package_dir: Optional[str] = None) -> bool:
    return installed_path(entry, package_dir).is_file()


# --------------------------------------------------------------------------- #
# Install / uninstall / list
# --------------------------------------------------------------------------- #

def _nested_folder_targets(ref: Ref, index: List[IndexEntry]) -> List[IndexEntry]:
    """Entries under ``<folder>/<name>/`` — plugin tool folders like
    ``@plugins/dorkbuilder`` resolve to every file in that subfolder."""
    prefix = f"{ref.name}/"
    return [e for e in index
            if e.folder == ref.folder and e.name.startswith(prefix)]


def resolve_targets(raw: str, index: Optional[List[IndexEntry]] = None,
                    config: Optional[Dict] = None) -> List[IndexEntry]:
    """
    Resolve a reference to every index entry it covers.

    Handles file refs ('@cve/cve_1.txt', '@plugins/dorkbuilder/x.py'),
    whole-folder refs ('@cve', '@plugins') and plugin tool folders
    ('@plugins/dorkbuilder' → all files inside that subfolder).
    """
    entries = index if index is not None else load_index(config=config)
    ref = parse_ref(raw)

    if ref.name is None:
        folder = resolve_folder(raw, index=entries)
        targets = [e for e in entries if e.folder == folder]
        if not targets:
            raise RefNotFound(f"Folder '@{folder}' has no installable files.")
        return targets

    try:
        return [resolve_entry(raw, index=entries)]
    except RefNotFound as exc:
        nested = _nested_folder_targets(ref, entries)
        if nested:
            return nested
        raise exc


def install(raw: str, *, force: bool = False, package_dir: Optional[str] = None,
            repo: Optional[str] = None, config: Optional[Dict] = None) -> List[InstallOutcome]:
    """
    Install a package reference into the local store.

    Accepts file refs ('@cve/cve_1.txt', 'c@cve_1.txt') and folder refs
    ('@cve', '@plugins/dorkbuilder', '@plugins') — folder refs install
    every file the reference covers.
    """
    entries = load_index(repo=repo, config=config)
    targets = resolve_targets(raw, index=entries)

    store = get_package_dir(package_dir)
    outcomes: List[InstallOutcome] = []
    for entry in targets:
        src = source_path(entry, repo=repo, config=config)
        if not src.is_file():
            raise PackageError(
                f"Source file missing in Atdork-DB: {entry.ref} "
                "(index out of date? run 'atdork index --build')"
            )
        dest = store / entry.folder / entry.name

        if dest.is_file() and not force:
            try:
                if sha256_file(dest) == sha256_file(src):
                    outcomes.append(InstallOutcome(entry, dest, "exists"))
                    continue
            except OSError:  # unreadable dest → fall through to overwrite
                pass

        src_sha = sha256_file(src)
        if entry.sha256 and src_sha != entry.sha256:
            logger.warning(
                "%s: checksum differs from the index (stale index? "
                "run 'atdork index --build')", entry.ref,
            )

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        if sha256_file(dest) != src_sha:  # pragma: no cover - disk failure guard
            dest.unlink(missing_ok=True)
            raise PackageError(f"Checksum verification failed after copy: {entry.ref}")
        status = "updated" if force else "installed"
        outcomes.append(InstallOutcome(entry, dest, status))
    return outcomes


def uninstall(raw: str, *, package_dir: Optional[str] = None,
              config: Optional[Dict] = None) -> Tuple[List[IndexEntry], List[IndexEntry]]:
    """
    Remove installed copies from the local store.

    Returns (removed, not_installed) — folder refs remove every member.
    """
    try:
        entries = load_index(config=config)
    except PackageError:
        entries = []
    ref = parse_ref(raw)

    if ref.name is None:
        if not entries:
            raise PackageError("Index unavailable; cannot expand folder reference.")
        folder = resolve_folder(raw, index=entries)
        targets = [e for e in entries if e.folder == folder]
    elif entries:
        try:
            targets = [resolve_entry(raw, index=entries)]
        except RefNotFound as exc:
            nested = _nested_folder_targets(ref, entries)
            if not nested:
                raise exc
            targets = nested
    else:  # index missing — canonical @folder/file only
        if not (ref.folder and ref.exact_folder and ref.name):
            raise PackageError("Index unavailable; only canonical '@folder/file' refs work.")
        targets = [IndexEntry(ref.folder, ref.name, "", 0, 0)]

    removed, missing = [], []
    store = get_package_dir(package_dir)
    for entry in targets:
        path = store / entry.folder / entry.name
        if path.is_file():
            path.unlink()
            # prune empty folders
            parent = path.parent
            try:
                parent.rmdir()
            except OSError:
                pass
            removed.append(entry)
        else:
            missing.append(entry)
    return removed, missing


def list_installed(package_dir: Optional[str] = None,
                   config: Optional[Dict] = None) -> List[InstalledPackage]:
    """List packages present in the local store, compared against the index."""
    store = get_package_dir(package_dir)
    if not store.is_dir():
        return []

    try:
        index = {(e.folder, e.name): e for e in load_index(config=config)}
    except PackageError:
        index = {}

    result: List[InstalledPackage] = []
    for path in sorted(store.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in VALID_EXTS:
            continue
        rel = path.relative_to(store)
        if len(rel.parts) < 2:
            continue
        folder = rel.parts[0]
        name = "/".join(rel.parts[1:])   # plugins nest: @plugins/<tool>/file.py
        digest = sha256_file(path)
        lines = count_dork_lines(path)
        entry = index.get((folder, name))
        if entry is None:
            status = "orphan"
        elif entry.sha256 and digest != entry.sha256:
            status = "modified"
        else:
            status = "ok"
        result.append(InstalledPackage(
            folder=folder, name=name, path=path,
            size_bytes=path.stat().st_size, dork_lines=lines, status=status,
        ))
    return result


# --------------------------------------------------------------------------- #
# Search / batch file resolution
# --------------------------------------------------------------------------- #

def search(query: str, index: Optional[List[IndexEntry]] = None,
           config: Optional[Dict] = None) -> List[IndexEntry]:
    """Rank index entries whose ref/description contain the query tokens."""
    entries = index if index is not None else load_index(config=config)
    tokens = [t for t in re.split(r"\s+", (query or "").strip().lower()) if t]
    if not tokens:
        return []
    scored: List[Tuple[int, IndexEntry]] = []
    for entry in entries:
        hay = f"{entry.ref} {entry.description}".lower()
        score = sum(1 for t in tokens if t in hay)
        if score:
            scored.append((score, entry))
    scored.sort(key=lambda pair: (-pair[0], pair[1].ref))
    return [e for _, e in scored]


def resolve_batch_file(spec: str, config: Optional[Dict] = None) -> Path:
    """
    Resolve --batch-file into a readable path.

    Order: existing local path → installed copy → Atdork-DB checkout.
    Raises FileNotFoundError/RefError with a hint when nothing matches.
    """
    local = Path(os.path.expanduser(spec))
    if local.is_file():
        return local.resolve()

    raw = spec.strip()
    # Canonical refs can resolve straight from the store, even without an index.
    try:
        ref = parse_ref(raw)
    except RefError:
        ref = None
    if ref is not None and ref.name and ref.name.lower().endswith(".py"):
        raise RefError(
            f"'{raw}' is a plugin module, not a dork file. Install it with "
            f"'atdork install @plugins/{ref.name.split('/', 1)[0]}' and run it "
            f"via its --<plugin> flags instead of loading it as a batch."
        )
    store = get_package_dir()
    if ref is not None and ref.exact_folder and ref.folder and ref.name:
        if not _safe(ref.name):
            raise RefError(f"Unsafe package reference: '{raw}'")
        direct = store / ref.folder / ref.name
        if direct.is_file():
            return direct

    try:
        entries = load_index(config=config)
        entry = resolve_entry(raw, index=entries)
    except DBRepoNotFound:
        raise FileNotFoundError(
            f"Batch file not found: '{spec}' (not a local file, and "
            "Atdork-DB repository is unavailable — install it first with "
            "'atdork install ...')."
        )
    except RefError:
        # still try a canonical store path already handled above; give up
        raise

    installed = installed_path(entry)
    if installed.is_file():
        return installed
    src = source_path(entry, config=config)
    if src.is_file():
        logger.info("Batch file resolved from Atdork-DB (not installed): %s", entry.ref)
        return src
    raise FileNotFoundError(
        f"Package '{entry.ref}' is neither installed nor present in Atdork-DB. "
        f"Run 'atdork install {entry.ref}'."
    )


# --------------------------------------------------------------------------- #
# Index build / update
# --------------------------------------------------------------------------- #

_ACRONYMS = {
    "ghdb": "GHDB", "cve": "CVE", "lfi": "LFI", "rfi": "RFI", "cms": "CMS",
    "iot": "IoT", "aws": "AWS", "btc": "BTC", "ip": "IP", "ddg": "DDG",
}


def humanize(stem: str) -> str:
    """'Files-Containing-Passwords' -> 'Files Containing Passwords'."""
    words: List[str] = []
    for word in re.split(r"[-_\s]+", stem):
        if not word:
            continue
        lower = word.lower()
        if lower in _ACRONYMS:
            words.append(_ACRONYMS[lower])
        else:
            words.append(word[:1].upper() + word[1:])
    return " ".join(words)


def build_index(repo: Optional[str] = None, config: Optional[Dict] = None) -> Dict[str, object]:
    """
    Scan @folder data files in the Atdork-DB checkout and write Index.idn.

    Layout is flat (@folder/file); @plugins additionally allows tool
    subfolders (@plugins/<tool>/*.py) — their index name keeps the relative
    path. Returns stats: {'path', 'entries', 'folders', 'total_dorks'}.
    """
    root = find_db_repo(repo)
    entries: List[IndexEntry] = []
    skipped_nested = 0
    for folder in sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith("@")):
        if folder.name == PLUGIN_FOLDER:
            # Plugin tools may nest: @plugins/<tool>/file.py
            candidates = sorted(
                p for p in folder.rglob("*")
                if p.is_file() and not p.name.startswith(".")
                and not any(part.startswith(".") or part == "__pycache__"
                            for part in p.relative_to(folder).parts[:-1])
            )
        else:
            candidates = [p for p in sorted(folder.iterdir())
                          if p.is_file() and not p.name.startswith(".")]
        for path in candidates:
            if path.suffix.lower() not in VALID_EXTS:
                continue
            if path.parent != folder and folder.name != PLUGIN_FOLDER:  # pragma: no cover - flat folders
                skipped_nested += 1
                continue
            entries.append(IndexEntry(
                folder=folder.name[1:],
                name=path.relative_to(folder).as_posix(),
                sha256=sha256_file(path),
                size_bytes=path.stat().st_size,
                dork_lines=count_dork_lines(path),
                description=humanize(os.path.splitext(path.name)[0]),
            ))
    if not entries:
        raise PackageError(f"No package files found under @folders in {root}.")

    entries.sort(key=lambda e: e.ref)
    total_dorks = sum(e.dork_lines for e in entries)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = [
        f"# {INDEX_HEADER} v1",
        f"# generated: {now}",
        f"# entries: {len(entries)}",
        f"# total-dorks: {total_dorks}",
    ]
    for e in entries:
        lines.append(
            f"{e.ref}{INDEX_FIELD_SEPARATOR}{e.sha256}{INDEX_FIELD_SEPARATOR}"
            f"{e.size_bytes}{INDEX_FIELD_SEPARATOR}{e.dork_lines}{INDEX_FIELD_SEPARATOR}"
            f"{e.description}"
        )

    path = index_file(root)
    tmp = path.with_suffix(".idn.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(path)

    logger.info("Index built: %d entries, %d dorks → %s", len(entries), total_dorks, path)
    if skipped_nested:  # pragma: no cover - flat layout is enforced
        logger.warning("%d nested files skipped (index is flat: @folder/file).", skipped_nested)
    return {
        "path": str(path),
        "entries": len(entries),
        "folders": len({e.folder for e in entries}),
        "total_dorks": total_dorks,
    }


def update_repo(config: Optional[Dict] = None) -> Tuple[bool, str]:
    """
    Refresh the Atdork-DB checkout ('git pull --ff-only').

    Returns (ok, message). Works only for git checkouts; otherwise the
    caller is told to update manually.
    """
    root = find_db_repo()
    if not (root / ".git").exists():
        return False, f"{root} is not a git checkout — update it manually."
    git = shutil.which("git")
    if not git:
        return False, "git executable not found in PATH."
    try:
        proc = subprocess.run(
            [git, "-C", str(root), "pull", "--ff-only"],
            capture_output=True, text=True, timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"git pull failed: {exc}"
    output = (proc.stdout + proc.stderr).strip()
    if proc.returncode != 0:
        return False, output or f"git pull exited with code {proc.returncode}"
    return True, output or "Already up to date."
