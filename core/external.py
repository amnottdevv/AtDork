"""
Atdork external plugin distribution (core/external.py)

Install plugin tools from anywhere — a raw ``.py`` URL, a git repository, or a
third-party registry declared under ``plugins.sources`` in the configuration:

    atdork install https://raw.githubusercontent.com/user/repo/main/tool/tool.py
    atdork install https://github.com/user/atdork-plugins#my-tool
    atdork install --source mine @plugins/my-tool

Everything lands in the local store (``<store>/plugins/<tool>/…``) through the
same contract gate used for Atdork-DB plugins: metadata is read with AST (the
file is never executed), the name must be valid, and files are capped in size.
Unlike the curated Atdork-DB index, external sources verify **every** file
against the checksum recorded in their own ``Index.idn`` and refuse a mismatch.

Registries use the Atdork-DB layout — an ``Index.idn`` plus
``@plugins/<tool>/…`` folders — so ``atdork plugins publish`` turns any repo
into a registry with a single git push.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from core.package_manager import (
    INDEX_FIELD_SEPARATOR,
    INDEX_HEADER,
    INDEX_NAME,
    IndexEntry,
    InstallOutcome,
    PackageError,
    get_package_dir,
    parse_index_file,
    parse_ref,
    resolve_targets,
    sha256_file,
)
from core.plugins import PluginError, load_plugin_meta, validate_meta

logger = logging.getLogger(__name__)

STORE_PLUGIN_FOLDER = "plugins"      # store layout is @-less
MAX_FILE_BYTES = 1 << 20             # 1 MiB per file
MAX_TOOL_BYTES = 8 << 20             # 8 MiB per tool folder
HTTP_TIMEOUT = 20                    # seconds
GIT_TIMEOUT = 300                    # seconds
SKIP_PARTS = {"__pycache__"}

_URL_RE = re.compile(r"^(?:https?|file|ssh)://", re.IGNORECASE)
_SCP_LIKE_RE = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+:")


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #

class ExternalError(PackageError):
    """An external plugin source could not be used safely."""


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

def looks_like_url(spec: str) -> bool:
    """True when *spec* is a URL (http(s)/file/ssh) rather than a package ref."""
    spec = (spec or "").strip()
    return bool(_URL_RE.match(spec) or _SCP_LIKE_RE.match(spec))


def _is_raw_py_url(url: str) -> bool:
    path = urllib.parse.urlsplit(url).path
    return path.lower().endswith(".py")


def _require_git() -> str:
    git = shutil.which("git")
    if not git:
        raise ExternalError(
            "git is required to install from a repository URL but was not "
            "found in PATH."
        )
    return git


@contextmanager
def _temp_dir(prefix: str = "atdork-ext-") -> Iterator[Path]:
    root = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _download(url: str) -> bytes:
    """Fetch a single module: ``file://`` reads the path, http(s) downloads it."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme in ("", "file"):
        path = Path(urllib.request.url2pathname(parts.path))
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise ExternalError(f"cannot read {url}: {exc}") from exc
    elif parts.scheme in ("http", "https"):
        request = urllib.request.Request(
            url, headers={"User-Agent": "atdork-external/1.0"})
        try:
            # Only http(s) reaches urlopen: the scheme is allowlisted above.
            with urllib.request.urlopen(  # nosec B310
                    request, timeout=HTTP_TIMEOUT) as response:
                data = response.read(MAX_FILE_BYTES + 1)
        except urllib.error.URLError as exc:
            raise ExternalError(f"cannot download {url}: {exc.reason}") from exc
        except OSError as exc:
            raise ExternalError(f"cannot download {url}: {exc}") from exc
    else:
        raise ExternalError(
            f"unsupported URL scheme '{parts.scheme}://' (use http(s) or file)."
        )
    if len(data) > MAX_FILE_BYTES:
        raise ExternalError(
            f"{url} is larger than {MAX_FILE_BYTES // 1024} KiB — refusing."
        )
    return data


def _git_clone(url: str, dest: Path, ref: Optional[str] = None) -> None:
    git = _require_git()
    cmd = [git, "clone", "--depth", "1", "--quiet"]
    if ref:
        cmd += ["--branch", str(ref)]
    cmd += ["--", url, str(dest)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=GIT_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ExternalError(f"git clone failed for {url}: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise ExternalError(f"git clone failed for {url}: {detail}")


def _git_pull(dest: Path) -> None:
    git = _require_git()
    try:
        proc = subprocess.run(
            [git, "-C", str(dest), "pull", "--ff-only", "--quiet"],
            capture_output=True, text=True, timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("source refresh failed for %s: %s", dest, exc)
        return
    if proc.returncode != 0:
        logger.warning("source refresh failed for %s: %s", dest,
                       (proc.stderr or proc.stdout or "").strip())


def _plugin_meta(path: Path, label: str) -> Dict[str, Any]:
    """Read + validate PLUGIN metadata, raising ExternalError on any problem."""
    try:
        meta = load_plugin_meta(path)
    except PluginError as exc:
        raise ExternalError(f"{label}: {exc}") from exc
    errors = validate_meta(meta, label)
    if errors:
        raise ExternalError("invalid plugin metadata: " + "; ".join(errors))
    return meta


def _tool_candidates(root: Path) -> Tuple[List[Tuple[Path, Dict[str, Any]]],
                                          List[str]]:
    """(valid, invalid) plugin entry points found anywhere under *root*."""
    valid: List[Tuple[Path, Dict[str, Any]]] = []
    invalid: List[str] = []
    for py in sorted(root.rglob("*.py")):
        rel = py.relative_to(root)
        if py.name.startswith("_") or py.name == "conftest.py":
            continue
        if any(part.startswith(".") or part in SKIP_PARTS
               for part in rel.parts[:-1]):
            continue
        try:
            meta = load_plugin_meta(py)
        except PluginError:
            continue   # helper module, not a plugin entry point
        errors = validate_meta(meta, rel.as_posix())
        if errors:
            invalid.append("; ".join(errors))
            continue
        valid.append((py, meta))
    return valid, invalid


def _select_tool(root: Path, subpath: str) -> List[Tuple[Path, Dict[str, Any]]]:
    """Resolve a '#subpath' selector to plugin entry points inside *root*."""
    root = root.resolve()
    target = (root / subpath).resolve()
    if target != root and root not in target.parents:
        raise ExternalError(f"subpath escapes the repository: {subpath!r}")
    if target.is_file():
        if target.suffix.lower() != ".py":
            raise ExternalError(f"not a plugin module: {subpath!r}")
        return [(target, _plugin_meta(target, subpath))]
    if not target.is_dir():
        raise ExternalError(f"no such subpath in the repository: {subpath!r}")
    valid, invalid = _tool_candidates(target)
    if not valid:
        detail = "; ".join(invalid) if invalid else "no PLUGIN metadata found"
        raise ExternalError(f"{subpath!r}: no installable plugin found ({detail})")
    if len(valid) > 1:
        opts = sorted(str(p.relative_to(root)) for p, _ in valid)
        raise ExternalError(
            f"{subpath!r} contains {len(valid)} plugins; point at one file: "
            + ", ".join(f"#{o}" for o in opts)
        )
    return valid


def _install_tool_dir(tool_dir: Path, meta: Dict[str, Any], *,
                      force: bool, package_dir: Optional[str],
                      label: str) -> List[InstallOutcome]:
    """Copy one tool folder into the store, capped and checksum-verified."""
    name = str(meta["name"])
    store = get_package_dir(package_dir) / STORE_PLUGIN_FOLDER / name
    files = [p for p in sorted(tool_dir.rglob("*"))
             if p.is_file()
             and not p.name.startswith(".")
             and not any(part.startswith(".") or part in SKIP_PARTS
                         for part in p.relative_to(tool_dir).parts[:-1])]
    if not files:
        raise ExternalError(f"{label}: no files found in {tool_dir}")

    outcomes: List[InstallOutcome] = []
    total = 0
    for src in files:
        rel = src.relative_to(tool_dir).as_posix()
        size = src.stat().st_size
        if size > MAX_FILE_BYTES:
            raise ExternalError(
                f"{label}: {rel} is {size} bytes (limit {MAX_FILE_BYTES})."
            )
        total += size
        if total > MAX_TOOL_BYTES:
            raise ExternalError(
                f"{label}: tool exceeds the {MAX_TOOL_BYTES // (1 << 20)} MiB limit."
            )
        src_sha = sha256_file(src)
        dest = store / rel
        if dest.is_file() and not force and sha256_file(dest) == src_sha:
            status = "exists"
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            if sha256_file(dest) != src_sha:  # pragma: no cover - disk guard
                dest.unlink(missing_ok=True)
                raise ExternalError(f"checksum mismatch after copying {rel}")
            status = "updated" if force else "installed"
        outcomes.append(InstallOutcome(
            IndexEntry(
                folder=STORE_PLUGIN_FOLDER,
                name=f"{name}/{rel}",
                sha256=src_sha,
                size_bytes=size,
                dork_lines=0,     # plugin files are code/assets, not dorks
                description=str(meta.get("description", "")),
            ),
            dest, status))
    return outcomes


# --------------------------------------------------------------------------- #
# Install from a URL
# --------------------------------------------------------------------------- #

def install_url(spec: str, *, git_ref: Optional[str] = None, force: bool = False,
                package_dir: Optional[str] = None,
                config: Optional[Dict[str, Any]] = None) -> List[InstallOutcome]:
    """Install a plugin from a raw ``.py`` URL or a git repository URL.

    Repository URLs accept a ``#subpath`` fragment selecting a tool folder or
    a single module; without a fragment the repo must contain exactly one
    plugin. ``git_ref`` pins a branch or tag.
    """
    url, _, fragment = (spec or "").strip().partition("#")
    if not looks_like_url(url):
        raise ExternalError(f"not a URL: {spec!r}")

    if _is_raw_py_url(url):
        if fragment:
            raise ExternalError(
                "'#subpath' selects a folder and only applies to repository URLs."
            )
        return _install_py_url(url, force=force, package_dir=package_dir)

    with _temp_dir() as tmp:
        root = tmp / "repo"
        _git_clone(url, root, ref=git_ref)
        if fragment:
            picked = _select_tool(root, fragment)
        else:
            valid, invalid = _tool_candidates(root)
            if not valid:
                if invalid:
                    raise ExternalError(
                        f"{url}: invalid plugin metadata: " + "; ".join(invalid))
                raise ExternalError(
                    f"{url}: no installable plugin found "
                    "(no PLUGIN metadata found)")
            if len(valid) > 1:
                opts = sorted(
                    str(p.parent.relative_to(root)) or "." for p, _ in valid)
                raise ExternalError(
                    f"{url} contains {len(valid)} plugins; pick one with "
                    "'#<subpath>': " + ", ".join(f"#{o}" for o in opts)
                )
            picked = valid
        outcomes: List[InstallOutcome] = []
        for py, meta in picked:
            outcomes += _install_tool_dir(py.parent, meta, force=force,
                                          package_dir=package_dir,
                                          label=f"{url}#{py.name}")
        return outcomes


def _install_py_url(url: str, *, force: bool,
                    package_dir: Optional[str]) -> List[InstallOutcome]:
    data = _download(url)
    filename = Path(urllib.parse.urlsplit(url).path).name or "plugin.py"
    if not filename.lower().endswith(".py"):
        filename += ".py"
    with _temp_dir(prefix="atdork-ext-file-") as tmp:
        module = tmp / filename
        module.write_bytes(data)
        meta = _plugin_meta(module, url)
        return _install_tool_dir(tmp, meta, force=force,
                                 package_dir=package_dir, label=url)


# --------------------------------------------------------------------------- #
# Third-party registries (plugins.sources)
# --------------------------------------------------------------------------- #

def list_sources(config: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
    """Configured plugin sources: ``{name: {url, ref?, index?}}``."""
    if config is None:
        from core.config import get_setting
        config = get_setting("plugins")
    sources = config.get("sources") if isinstance(config, dict) else None
    if not isinstance(sources, dict):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for name, spec in sources.items():
        if isinstance(spec, dict) and isinstance(spec.get("url"), str):
            out[str(name)] = dict(spec)
    return out


def source_cache_dir(name: str, workspace: Any = None) -> Path:
    root = getattr(workspace, "root", None)
    if root is not None:
        return Path(root) / "cache" / "sources" / name
    return Path(os.path.expanduser("~/.cache/atdork/sources")) / name


def source_repo(name: str, *, config: Optional[Dict[str, Any]] = None,
                workspace: Any = None, update: bool = False) -> Path:
    """Clone (first use) or refresh the git repo behind a configured source."""
    configured = list_sources(config)
    spec = configured.get(name)
    if spec is None:
        known = ", ".join(sorted(configured)) or "(none configured)"
        raise ExternalError(
            f"unknown plugin source '{name}' (configured: {known}). Add it "
            "under plugins.sources in your configuration."
        )
    cache = source_cache_dir(name, workspace)
    if (cache / ".git").is_dir():
        if update:
            _git_pull(cache)
        return cache
    if cache.exists():
        shutil.rmtree(cache, ignore_errors=True)
    cache.parent.mkdir(parents=True, exist_ok=True)
    _git_clone(str(spec["url"]), cache, ref=spec.get("ref"))
    return cache


def install_from_source(source: str, raw_ref: str, *, force: bool = False,
                        package_dir: Optional[str] = None,
                        config: Optional[Dict[str, Any]] = None,
                        workspace: Any = None) -> List[InstallOutcome]:
    """Install refs from a third-party registry (same layout as Atdork-DB)."""
    spec = list_sources(config).get(source)
    repo = source_repo(source, config=config, workspace=workspace, update=True)
    index_name = str((spec or {}).get("index") or INDEX_NAME)
    index_path = repo / index_name
    if not index_path.is_file():
        raise ExternalError(
            f"source '{source}': {index_name} not found in {repo}. The repo "
            "must ship an Index.idn (see 'atdork plugins publish')."
        )
    entries = parse_index_file(index_path)
    if not entries:
        raise ExternalError(f"source '{source}': {index_name} contains no entries.")

    targets = resolve_targets(raw_ref, index=entries)
    store = get_package_dir(package_dir)
    outcomes: List[InstallOutcome] = []
    for entry in targets:
        src = repo / f"@{entry.folder}" / entry.name
        if not src.is_file():
            raise ExternalError(
                f"source '{source}': {entry.ref} is listed in {index_name} but "
                "missing from the checkout."
            )
        digest = sha256_file(src)
        if entry.sha256 and digest != entry.sha256:
            raise ExternalError(
                f"source '{source}': checksum mismatch for {entry.ref} "
                f"(index {entry.sha256[:12]}…, file {digest[:12]}…) — refusing "
                "to install."
            )
        dest = store / entry.folder / entry.name
        if dest.is_file() and not force and sha256_file(dest) == digest:
            outcomes.append(InstallOutcome(entry, dest, "exists"))
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        outcomes.append(InstallOutcome(
            entry, dest, "updated" if force else "installed"))
    return outcomes


# --------------------------------------------------------------------------- #
# Publishing (build Index.idn lines for your own registry)
# --------------------------------------------------------------------------- #

def _publish_entries(tool_dir: Path) -> List[IndexEntry]:
    files = [p for p in sorted(tool_dir.rglob("*"))
             if p.is_file()
             and not p.name.startswith(".")
             and not any(part.startswith(".") or part in SKIP_PARTS
                         for part in p.relative_to(tool_dir).parts[:-1])]
    if not files:
        raise ExternalError(f"no files to publish in {tool_dir}")

    tool = tool_dir.name
    description = ""
    entry_py = tool_dir / f"{tool}.py"
    if entry_py.is_file():
        try:
            description = str(load_plugin_meta(entry_py).get("description", ""))
        except PluginError:
            description = ""
    entries = []
    for path in files:
        rel = path.relative_to(tool_dir).as_posix()
        entries.append(IndexEntry(
            folder=STORE_PLUGIN_FOLDER,
            name=f"{tool}/{rel}",
            sha256=sha256_file(path),
            size_bytes=path.stat().st_size,
            dork_lines=0,
            description=description if rel.endswith(".py") else "",
        ))
    return entries


def _index_lines(entries: List[IndexEntry]) -> List[str]:
    return [
        f"{e.ref}{INDEX_FIELD_SEPARATOR}{e.sha256}{INDEX_FIELD_SEPARATOR}"
        f"{e.size_bytes}{INDEX_FIELD_SEPARATOR}{e.dork_lines}{INDEX_FIELD_SEPARATOR}"
        f"{e.description}"
        for e in entries
    ]


def _read_index_rows(path: Path) -> Tuple[List[str], List[str]]:
    """(header comment lines, entry rows) of an existing Index.idn."""
    header: List[str] = []
    rows: List[str] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                if not re.match(r"#\s*(generated|entries|total-dorks):", line):
                    header.append(line)
            elif line.strip():
                rows.append(line)
    return header, rows


def publish(raw_ref: str, *, repo: Optional[str] = None,
            index_path: Optional[str] = None, write: bool = False,
            package_dir: Optional[str] = None,
            config: Optional[Dict[str, Any]] = None
            ) -> Tuple[List[str], Optional[Path]]:
    """Generate index lines for a plugin tool folder.

    Source folder comes from the Atdork-DB checkout (``@plugins/<tool>``) or,
    failing that, from the local store. Returns (lines, written_path).
    """
    ref = parse_ref(raw_ref)
    if ref.folder != STORE_PLUGIN_FOLDER or not ref.name:
        raise ExternalError(
            "publish expects a plugin tool folder ref, e.g. '@plugins/mytool'."
        )
    tool = ref.name
    candidates = []
    try:
        from core.package_manager import find_db_repo
        candidates.append(find_db_repo(repo) / "@plugins" / tool)
    except PackageError:
        pass
    candidates.append(get_package_dir(package_dir) / STORE_PLUGIN_FOLDER / tool)

    tool_dir = next((c for c in candidates if c.is_dir()), None)
    if tool_dir is None:
        raise ExternalError(
            f"plugin folder '{tool}' not found (looked in the Atdork-DB "
            f"checkout and the store: {get_package_dir(package_dir)})."
        )

    entries = _publish_entries(tool_dir)
    lines = _index_lines(entries)
    if not write:
        return lines, None

    if index_path:
        target = Path(os.path.expanduser(index_path))
    elif repo:
        target = Path(os.path.expanduser(repo)) / INDEX_NAME
    else:
        try:
            from core.package_manager import find_db_repo
            target = find_db_repo(repo) / INDEX_NAME
        except PackageError:
            raise ExternalError(
                "cannot locate Index.idn to write — pass --index PATH."
            )

    header, rows = _read_index_rows(target)
    prefix = f"@plugins/{tool}/"
    rows = [r for r in rows if not r.startswith(prefix)]
    rows += lines
    rows.sort(key=lambda r: r.split(INDEX_FIELD_SEPARATOR, 1)[0])

    total_dorks = 0
    for row in rows:
        parts = row.split(INDEX_FIELD_SEPARATOR)
        if len(parts) >= 4:
            try:
                total_dorks += int(parts[3])
            except ValueError:
                continue
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = (header or [f"# {INDEX_HEADER} v1"])
    out += [
        f"# generated: {now}",
        f"# entries: {len(rows)}",
        f"# total-dorks: {total_dorks}",
    ] + rows

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".idn.tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    tmp.replace(target)
    return lines, target
