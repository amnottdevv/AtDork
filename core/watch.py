"""
Atdork watch mode (core/watch.py)

Cron-friendly monitoring: register a watch (a name plus the dorks to run), then
``atdork watch run <name>`` re-runs those dorks, compares the result URLs with
the previous run and reports **only the new findings** — on the console and,
when a webhook target is configured, through ``core/notification.py``
(``--notify discord:|slack:|telegram:``).

Design notes:
  * One-shot by design: no daemon, no scheduler inside AtDork. Put
    ``atdork watch run <name>`` in cron/systemd and it stays stateless between
    runs.
  * State lives in ``<env>/state/watch/<name>.json`` (or
    ``~/.atdork/state/watch/``), holding both the definition and the seen-URL
    history (bounded to :data:`MAX_SEEN` entries).
  * URLs are normalized before hashing, so ``http://WWW.Example.com/a/?utm=1``
    and ``https://example.com/a`` are the same finding.
  * The first run records a **baseline** (no "new" spam) — later runs report
    the delta only.
  * Watch runs never use the search cache: monitoring must always hit the
    network to notice changes.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from core.batch_runner import load_queries_from_file, run_batch
from core.database_dork import load_database_dorks
from core.notification import send_notification

logger = logging.getLogger(__name__)

WATCH_FOLDER = "watch"           # <state_dir>/watch/<name>.json
MAX_SEEN = 10000                 # bounded URL history per watch
MAX_NOTIFY_URLS = 10             # links listed in one notification
MAX_STORED_NEW = 25              # last new URLs kept for `watch show`
STATE_VERSION = 1

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_URL_KEYS = ("href", "url", "link")
_TRACKING_PARAMS = {"gclid", "fbclid", "msclkid", "igshid", "mc_cid", "mc_eid", "yclid"}


class WatchError(Exception):
    """Raised for invalid watch definitions, state problems, or bad options."""


# --------------------------------------------------------------------------- #
# Naming, paths and state
# --------------------------------------------------------------------------- #

def validate_name(name: str) -> str:
    """Return a validated watch name (letters, digits, '.', '_', '-')."""
    name = (name or "").strip()
    if not _NAME_RE.fullmatch(name):
        raise WatchError(
            f"invalid watch name '{name}': use letters, digits, '.', '_' or "
            "'-' (max 64 chars)."
        )
    return name


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def state_dir(workspace: Any = None) -> Path:
    """``<env>/state/watch`` — or ``~/.atdork/state/watch`` without an env."""
    root = getattr(workspace, "state_dir", None)
    if root:
        return Path(root) / WATCH_FOLDER
    return Path.home() / ".atdork" / "state" / WATCH_FOLDER


def state_path(name: str, workspace: Any = None) -> Path:
    return state_dir(workspace) / f"{validate_name(name)}.json"


def load_watch(name: str, workspace: Any = None) -> Dict[str, Any]:
    """Load a watch definition + history; raises WatchError when unknown."""
    path = state_path(name, workspace)
    if not path.is_file():
        raise WatchError(
            f"watch '{name}' not found ({path}). Create it with "
            f"'atdork watch add {name} --dork \"…\"'."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WatchError(f"cannot read watch '{name}' ({path}): {exc}") from exc
    if not isinstance(data, dict):
        raise WatchError(f"watch '{name}' state is not a JSON object ({path}).")
    data.setdefault("name", name)
    return data


def save_watch(record: Dict[str, Any], workspace: Any = None) -> Path:
    """Atomically write a watch record (definition + history)."""
    name = validate_name(str(record.get("name", "")))
    path = state_path(name, workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(record)
    payload["name"] = name
    payload["version"] = STATE_VERSION
    payload["updated"] = now_iso()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    tmp.replace(path)
    return path


def list_watches(workspace: Any = None) -> List[Dict[str, Any]]:
    """Every saved watch, sorted by name (corrupt files are skipped)."""
    directory = state_dir(workspace)
    if not directory.is_dir():
        return []
    records: List[Dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("Skipping corrupt watch state: %s", path)
            continue
        if isinstance(data, dict):
            data.setdefault("name", path.stem)
            records.append(data)
    return records


def add_watch(name: str, *, dorks: Sequence[str] = (),
              batch_files: Sequence[str] = (), database: Optional[str] = None,
              notify: Optional[str] = None,
              options: Optional[Dict[str, Any]] = None,
              workspace: Any = None) -> Dict[str, Any]:
    """Create a watch — or merge new sources into an existing one.

    The seen-URL history (and the baseline) is preserved when merging, so
    adding a dork to a live watch never re-notifies old findings.
    """
    name = validate_name(name)
    clean_dorks = [d.strip() for d in dorks if str(d).strip()]
    clean_files = [str(f).strip() for f in batch_files if str(f).strip()]
    clean_db = (database or "").strip() or None
    if not (clean_dorks or clean_files or clean_db):
        raise WatchError(
            "a watch needs at least one dork source: --dork, --batch-file or "
            "--database-dork."
        )

    try:
        record = load_watch(name, workspace)
        created = record.get("created") or now_iso()
    except WatchError:
        record = {"name": name, "created": now_iso(), "runs": 0, "seen": []}
        created = record["created"]

    record["created"] = created
    record["dorks"] = _merge_unique(record.get("dorks") or [], clean_dorks)
    record["batch_files"] = _merge_unique(record.get("batch_files") or [],
                                          clean_files)
    if clean_db:
        record["database"] = clean_db
    if notify:
        record["notify"] = notify.strip()
    if options:
        merged_options = dict(record.get("options") or {})
        merged_options.update({k: v for k, v in options.items() if v is not None})
        record["options"] = merged_options
    record.setdefault("seen", [])
    save_watch(record, workspace)
    return record


def remove_watch(name: str, workspace: Any = None) -> Path:
    """Delete a watch definition and its history."""
    path = state_path(name, workspace)
    if not path.is_file():
        raise WatchError(f"watch '{name}' not found ({path}).")
    path.unlink()
    return path


def _merge_unique(existing: Iterable[Any], extra: Iterable[Any]) -> List[str]:
    out = [str(item) for item in existing if str(item).strip()]
    for item in extra:
        text = str(item)
        if text not in out:
            out.append(text)
    return out


# --------------------------------------------------------------------------- #
# Dork sources + result keys
# --------------------------------------------------------------------------- #

def resolve_queries(record: Dict[str, Any],
                    db_path: Optional[str] = None) -> List[str]:
    """Every dork a watch should run (dorks + batch files + database spec)."""
    name = record.get("name", "?")
    queries: List[str] = [str(d) for d in (record.get("dorks") or [])]

    for raw_path in record.get("batch_files") or []:
        path = Path(os.path.expanduser(str(raw_path)))
        if not path.is_file():
            raise WatchError(
                f"watch '{name}': batch file not found: {raw_path}"
            )
        try:
            queries.extend(load_queries_from_file(str(path)))
        except (OSError, ValueError) as exc:
            raise WatchError(
                f"watch '{name}': cannot read batch file {raw_path}: {exc}"
            ) from exc

    database = (record.get("database") or "").strip()
    if database:
        try:
            queries.extend(load_database_dorks(database, db_path=db_path))
        except (OSError, ValueError, FileNotFoundError) as exc:
            raise WatchError(
                f"watch '{name}': cannot load --database-dork "
                f"'{database}': {exc}"
            ) from exc

    unique = list(dict.fromkeys(q.strip() for q in queries if q and q.strip()))
    if not unique:
        raise WatchError(f"watch '{name}' has no dorks to run.")
    return unique


def normalize_url(url: str) -> str:
    """Canonical form of a result URL: used as the 'already seen' key."""
    text = (url or "").strip()
    if not text:
        return ""
    parts = urllib.parse.urlsplit(text)
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    if not scheme and not netloc:
        return "text:" + text.lower()          # not a URL — compare verbatim
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    if parts.query:
        pairs = [(k, v) for k, v in
                 urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
                 if not (k.lower().startswith("utm_")
                         or k.lower() in _TRACKING_PARAMS)]
        query = urllib.parse.urlencode(sorted(pairs))
    else:
        query = ""
    return urllib.parse.urlunsplit((scheme, netloc, path, query, ""))


def result_key(result: Dict[str, Any]) -> str:
    """Normalized URL of a result dict, or '' when it has no link."""
    for key in _URL_KEYS:
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return normalize_url(value)
    return ""


def _result_url(result: Dict[str, Any]) -> str:
    for key in _URL_KEYS:
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


# --------------------------------------------------------------------------- #
# Running
# --------------------------------------------------------------------------- #

def run_watch(name: str, *, workspace: Any = None, console: Any = None,
              case_modules: Optional[Dict] = None, concurrency: int = 1,
              search_kwargs: Optional[Dict[str, Any]] = None,
              notify_target: Optional[str] = None,
              dry_run: bool = False) -> Dict[str, Any]:
    """Run one watch cycle: search, diff against history, notify, save.

    Returns a report: ``{name, queries, results, new, new_urls, baseline,
    failed, notify, notified, dry_run}`` where ``new`` holds the new result
    dicts. A quiet run (no new findings, not a baseline) does not notify.
    """
    name = validate_name(name)
    record = load_watch(name, workspace)
    queries = resolve_queries(record)

    if dry_run:
        if console is not None:
            console.print(f"[bold cyan]watch {name}[/bold cyan] — "
                          f"{len(queries)} dork(s) resolved (dry run, "
                          "nothing searched).")
            for query in queries[:5]:
                console.print(f"  [dim]{query}[/dim]")
            if len(queries) > 5:
                console.print(f"  [dim]… {len(queries) - 5} more[/dim]")
        return {"name": name, "queries": len(queries), "results": 0, "new": [],
                "new_urls": [], "baseline": False, "failed": 0,
                "notify": notify_target or record.get("notify"), "dry_run": True}

    options: Dict[str, Any] = dict(record.get("options") or {})
    options.update({k: v for k, v in (search_kwargs or {}).items()
                    if v is not None})

    # No cache: a monitored dork must be re-fetched, not answered from history.
    results_map = run_batch(
        queries,
        case_modules=case_modules,
        concurrency=concurrency,
        show_progress=False,
        **options,
    )

    failed = sum(1 for group in results_map.values() if not group)
    results = [res for group in results_map.values()
               for res in (group or []) if isinstance(res, dict)]

    seen: List[str] = [str(k) for k in (record.get("seen") or [])]
    seen_set = set(seen)
    baseline = int(record.get("runs") or 0) == 0

    new_keys: List[str] = []
    new_results: List[Dict[str, Any]] = []
    for res in results:
        key = result_key(res)
        if not key or key in seen_set or key in new_keys:
            continue
        new_keys.append(key)
        new_results.append(res)

    seen.extend(new_keys)
    if len(seen) > MAX_SEEN:
        seen = seen[-MAX_SEEN:]

    record["seen"] = seen
    record["runs"] = int(record.get("runs") or 0) + 1
    record["last_run"] = now_iso()
    record["last_queries"] = len(queries)
    record["last_results"] = len(results)
    record["last_failed"] = failed
    record["last_new"] = 0 if baseline else len(new_keys)
    record["last_new_urls"] = [_result_url(r) for r in new_results[:MAX_STORED_NEW]]
    if baseline:
        record["baseline_at"] = record["last_run"]

    report = {
        "name": name,
        "queries": len(queries),
        "results": len(results),
        "new": [] if baseline else new_results,
        "new_urls": [] if baseline else [u for u in
                                        (_result_url(r) for r in new_results)
                                        if u],
        "baseline": baseline,
        "failed": failed,
        "notify": notify_target or record.get("notify"),
        "dry_run": False,
    }

    save_watch(record, workspace)

    report["notified"] = False
    if console is not None:
        _print_report(console, report)

    # A quiet run stays quiet: only the baseline and real findings notify.
    if report["notify"] and (report["baseline"] or report["new"]):
        report["notified"] = _notify(report)
        if console is not None and report["notified"]:
            console.print(f"[dim]Notified: "
                          f"{report['notify'].split(':', 1)[0]}[/dim]")

    return report


def _print_report(console: Any, report: Dict[str, Any]) -> None:
    name = report["name"]
    if report["baseline"]:
        console.print(f"[bold cyan]watch {name}[/bold cyan] — baseline "
                      f"recorded: [green]{report['results']}[/green] result(s) "
                      f"from {report['queries']} dork(s).")
        console.print("[dim]Future runs report only new findings.[/dim]")
    else:
        count = len(report["new"])
        colour = "green" if count else "dim"
        console.print(f"[bold cyan]watch {name}[/bold cyan] — "
                      f"[{colour}]{count} new[/{colour}] of "
                      f"{report['results']} result(s) "
                      f"[dim]({report['queries']} dork(s))[/dim]")
        for url in report["new_urls"][:MAX_NOTIFY_URLS]:
            console.print(f"  [green]•[/green] {url}")
        if count > MAX_NOTIFY_URLS:
            console.print(f"  [dim]… and {count - MAX_NOTIFY_URLS} more[/dim]")
    if report["failed"]:
        console.print(f"[yellow]⚠ {report['failed']} dork(s) failed "
                      "(see --log-file)[/yellow]")


def _notification_body(report: Dict[str, Any]) -> str:
    name = report["name"]
    if report["baseline"]:
        return (f"[AtDork] watch '{name}' baseline recorded — "
                f"{report['results']} result(s) from {report['queries']} dork(s). "
                "Future runs report only new findings.")
    lines = [
        f"[AtDork] watch '{name}' — {len(report['new'])} new finding(s) "
        f"out of {report['results']} result(s) ({report['queries']} dork(s))"
    ]
    for url in report["new_urls"][:MAX_NOTIFY_URLS]:
        lines.append(f"• {url}")
    if len(report["new"]) > MAX_NOTIFY_URLS:
        lines.append(f"… and {len(report['new']) - MAX_NOTIFY_URLS} more")
    if report["failed"]:
        lines.append(f"({report['failed']} dork(s) failed)")
    return "\n".join(lines)


def _notify(report: Dict[str, Any]) -> bool:
    """Send the run summary through the existing webhook notifier."""
    try:
        ok = send_notification(report["notify"], _notification_body(report))
    except Exception as exc:  # never fail a run because a webhook is down
        logger.warning("watch '%s': notification failed: %s", report["name"], exc)
        return False
    if not ok:
        logger.warning("watch '%s': notification was rejected by the target",
                       report["name"])
    return bool(ok)


def run_all(*, workspace: Any = None, console: Any = None,
            **kwargs: Any) -> Tuple[List[Dict[str, Any]], List[Tuple[str, str]]]:
    """Run every saved watch. Returns (reports, [(name, error), …])."""
    reports: List[Dict[str, Any]] = []
    errors: List[Tuple[str, str]] = []
    for record in list_watches(workspace):
        name = str(record.get("name", ""))
        if console is not None:
            console.print("")
        try:
            reports.append(run_watch(name, workspace=workspace, console=console,
                                     **kwargs))
        except WatchError as exc:
            errors.append((name, str(exc)))
            if console is not None:
                console.print(f"[red]watch {name}: {exc}[/red]")
    return reports, errors


def summarize(record: Dict[str, Any]) -> str:
    """One-line description of a watch used by `watch list`."""
    sources: List[str] = []
    if record.get("dorks"):
        sources.append(f"{len(record['dorks'])} dork(s)")
    if record.get("batch_files"):
        sources.append(f"{len(record['batch_files'])} file(s)")
    if record.get("database"):
        sources.append(f"db:{record['database']}")
    runs = int(record.get("runs") or 0)
    state = "baseline" if not runs else f"{runs} run(s), last new: " \
                                       f"{int(record.get('last_new') or 0)}"
    return f"{', '.join(sources) or 'no sources'} — {state}"
