"""
Unit tests for watch mode (core/watch.py) and its CLI wiring
(atdork.watch_cli): one-shot monitoring that diffs result URLs against a saved
history and notifies through the existing webhook notifier.

No network: `core.watch.run_batch` is replaced with a fake, notifications are
captured, and HOME / state dirs live in tmp_path.
"""

import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from rich.console import Console

import core.watch as watch
from core.config import _CURRENT
from core.watch import (
    MAX_SEEN,
    WatchError,
    add_watch,
    list_watches,
    load_watch,
    normalize_url,
    remove_watch,
    resolve_queries,
    result_key,
    run_all,
    run_watch,
    state_dir,
    state_path,
    validate_name,
)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """HOME + config layer never leak between tests."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("ATDORK_ENV", raising=False)
    _CURRENT.clear()
    yield
    _CURRENT.clear()


def fake_console():
    buf = io.StringIO()
    return Console(file=buf, width=200), buf


def results(*urls, title="t"):
    return [{"title": f"{title}{i}", "href": url, "body": "b"}
            for i, url in enumerate(urls, 1)]


def install_run_batch(monkeypatch, mapping):
    """Replace core.watch.run_batch with a canned {dork: results} fake."""
    calls = {}

    def fake_run_batch(queries, **kwargs):
        calls["queries"] = list(queries)
        calls["kwargs"] = kwargs
        return {q: list(mapping.get(q, [])) for q in queries}

    monkeypatch.setattr(watch, "run_batch", fake_run_batch)
    return calls


def capture_notifications(monkeypatch):
    sent = []

    def fake_send(target, message):
        sent.append((target, message))
        return True

    monkeypatch.setattr(watch, "send_notification", fake_send)
    return sent


# --------------------------------------------------------------------------- #
# Names, paths, state
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", ["acme", "my.watch", "a_b-9", "A1"])
def test_validate_name_ok(name):
    assert validate_name(name) == name


@pytest.mark.parametrize("name", ["", " ", "-lead", "bad/name", "x" * 65, "a b"])
def test_validate_name_bad(name):
    with pytest.raises(WatchError, match="invalid watch name"):
        validate_name(name)


def test_state_path_without_env(tmp_path):
    assert state_dir() == Path.home() / ".atdork" / "state" / "watch"
    assert state_path("acme").name == "acme.json"


def test_state_path_with_workspace(tmp_path):
    ws = SimpleNamespace(state_dir=str(tmp_path / "env" / "state"))
    assert state_dir(ws) == tmp_path / "env" / "state" / "watch"
    assert state_path("acme", ws) == tmp_path / "env" / "state" / "watch" / "acme.json"


def test_load_watch_unknown():
    with pytest.raises(WatchError, match="not found"):
        load_watch("ghost")


def test_load_watch_corrupt(tmp_path):
    path = state_path("broken")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(WatchError, match="cannot read watch"):
        load_watch("broken")


def test_add_watch_requires_source():
    with pytest.raises(WatchError, match="at least one dork source"):
        add_watch("acme")


def test_add_watch_saves_record():
    record = add_watch("acme", dorks=["site:acme.com ext:env"],
                       notify="discord:https://hook",
                       options={"max_results": 20, "backend": "auto"})
    assert record["name"] == "acme"
    assert record["dorks"] == ["site:acme.com ext:env"]
    assert record["options"] == {"max_results": 20, "backend": "auto"}
    assert record["runs"] == 0

    on_disk = json.loads(state_path("acme").read_text(encoding="utf-8"))
    assert on_disk["notify"] == "discord:https://hook"
    assert on_disk["version"] == 1
    assert on_disk["created"]


def test_add_watch_merges_and_keeps_history():
    first = add_watch("acme", dorks=["d1"])
    first["seen"] = ["https://old.example/x"]
    watch.save_watch(first)

    merged = add_watch("acme", dorks=["d1", "d2"], batch_files=["dorks.txt"],
                       options={"region": "us-en"})
    assert merged["dorks"] == ["d1", "d2"]          # no duplicate
    assert merged["batch_files"] == ["dorks.txt"]
    assert merged["seen"] == ["https://old.example/x"]
    assert merged["created"] == first["created"]
    assert merged["options"] == {"region": "us-en"}


def test_add_watch_invalid_name():
    with pytest.raises(WatchError, match="invalid watch name"):
        add_watch("bad name", dorks=["d1"])


def test_list_and_remove_watch():
    add_watch("b", dorks=["db"])
    add_watch("a", dorks=["da"])
    assert [r["name"] for r in list_watches()] == ["a", "b"]

    removed = remove_watch("a")
    assert removed == state_path("a")
    assert [r["name"] for r in list_watches()] == ["b"]

    with pytest.raises(WatchError, match="not found"):
        remove_watch("a")


# --------------------------------------------------------------------------- #
# URL normalization
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("raw, expected", [
    ("https://WWW.Example.com/a/", "https://example.com/a"),
    ("http://example.com/a?utm_source=x&b=2&a=1", "http://example.com/a?a=1&b=2"),
    ("https://example.com/a#section", "https://example.com/a"),
    ("HTTPS://Example.com", "https://example.com/"),
    ("https://example.com/a?gclid=1", "https://example.com/a"),
    ("  https://example.com/a  ", "https://example.com/a"),
    ("not a url", "text:not a url"),
    ("", ""),
])
def test_normalize_url(raw, expected):
    assert normalize_url(raw) == expected


def test_result_key_prefers_url_keys():
    assert result_key({"href": "https://x.example/a"}) == "https://x.example/a"
    assert result_key({"url": "https://x.example/a"}) == "https://x.example/a"
    assert result_key({"link": "https://x.example/a"}) == "https://x.example/a"
    assert result_key({"title": "no link"}) == ""
    assert result_key({"href": "   "}) == ""


# --------------------------------------------------------------------------- #
# Dork resolution
# --------------------------------------------------------------------------- #

def test_resolve_queries_mixes_sources(tmp_path, monkeypatch):
    batch = tmp_path / "dorks.txt"
    batch.write_text("from-file\nshared\nd1\n", encoding="utf-8")
    monkeypatch.setattr(watch, "load_database_dorks",
                        lambda spec, db_path=None: ["from-db", "shared"])

    record = {"name": "acme", "dorks": ["d1", "shared"],
              "batch_files": [str(batch)], "database": "@ghdb/x"}
    assert resolve_queries(record) == ["d1", "shared", "from-file", "from-db"]


def test_resolve_queries_missing_batch_file(tmp_path):
    record = {"name": "acme", "dorks": [], "batch_files": [str(tmp_path / "nope.txt")]}
    with pytest.raises(WatchError, match="batch file not found"):
        resolve_queries(record)


def test_resolve_queries_database_error(monkeypatch):
    def boom(spec, db_path=None):
        raise FileNotFoundError("no such dork db")

    monkeypatch.setattr(watch, "load_database_dorks", boom)
    with pytest.raises(WatchError, match="cannot load --database-dork"):
        resolve_queries({"name": "acme", "dorks": [], "database": "@ghdb/x"})


def test_resolve_queries_empty():
    with pytest.raises(WatchError, match="no dorks to run"):
        resolve_queries({"name": "acme", "dorks": ["  "]})


# --------------------------------------------------------------------------- #
# run_watch
# --------------------------------------------------------------------------- #

def test_run_watch_dry_run_does_not_search(monkeypatch):
    add_watch("acme", dorks=["d1", "d2"])
    calls = install_run_batch(monkeypatch, {})
    console, buf = fake_console()

    report = run_watch("acme", console=console, dry_run=True)
    assert report["dry_run"] is True
    assert report["queries"] == 2
    assert "queries" not in calls
    assert "dry run" in buf.getvalue()


def test_run_watch_baseline_records_and_notifies(monkeypatch):
    add_watch("acme", dorks=["d1"], notify="discord:https://hook")
    install_run_batch(monkeypatch, {"d1": results("https://a.example/1",
                                                 "https://b.example/2")})
    sent = capture_notifications(monkeypatch)
    console, buf = fake_console()

    report = run_watch("acme", console=console)
    assert report["baseline"] is True
    assert report["new"] == []                     # baseline is not "new"
    assert report["results"] == 2
    assert report["notified"] is True
    assert "baseline" in buf.getvalue()
    assert len(sent) == 1 and "baseline recorded" in sent[0][1]

    record = load_watch("acme")
    assert record["runs"] == 1
    assert record["baseline_at"]
    assert len(record["seen"]) == 2


def test_run_watch_reports_only_new_findings(monkeypatch):
    add_watch("acme", dorks=["d1"], notify="discord:https://hook")
    install_run_batch(monkeypatch, {"d1": results("https://a.example/1")})
    sent = capture_notifications(monkeypatch)
    run_watch("acme")                               # baseline

    # Same URL (different case + tracking) plus one genuinely new URL.
    install_run_batch(monkeypatch, {"d1": results("https://A.example/1/?utm_source=n",
                                                  "https://new.example/x")})
    report = run_watch("acme")

    assert report["baseline"] is False
    assert report["new_urls"] == ["https://new.example/x"]
    assert report["notified"] is True
    assert "1 new finding" in sent[-1][1]
    assert "https://new.example/x" in sent[-1][1]

    record = load_watch("acme")
    assert record["runs"] == 2
    assert record["last_new"] == 1
    assert record["last_new_urls"] == ["https://new.example/x"]
    assert len(record["seen"]) == 2


def test_run_watch_quiet_run_does_not_notify(monkeypatch):
    add_watch("acme", dorks=["d1"], notify="discord:https://hook")
    mapping = {"d1": results("https://a.example/1")}
    install_run_batch(monkeypatch, mapping)
    sent = capture_notifications(monkeypatch)
    run_watch("acme")
    sent.clear()

    report = run_watch("acme")
    assert report["new"] == []
    assert report["notified"] is False
    assert sent == []


def test_run_watch_dedupes_within_one_run(monkeypatch):
    add_watch("acme", dorks=["d1", "d1"])
    install_run_batch(monkeypatch, {"d1": results("https://a.example/1",
                                                  "https://a.example/1/")})
    report = run_watch("acme")

    # The same dork twice collapses to one query; the two spellings of the URL
    # collapse to one finding.
    assert report["queries"] == 1
    assert len(load_watch("acme")["seen"]) == 1


def test_run_watch_counts_failed_dorks(monkeypatch):
    add_watch("acme", dorks=["ok", "bad"])
    install_run_batch(monkeypatch, {"ok": results("https://a.example/1")})
    report = run_watch("acme")
    assert report["failed"] == 1
    assert report["results"] == 1


def test_run_watch_passes_search_options(monkeypatch):
    add_watch("acme", dorks=["d1"],
              options={"max_results": 3, "backend": "auto", "region": "us-en"})
    calls = install_run_batch(monkeypatch, {"d1": []})

    run_watch("acme", concurrency=2,
              search_kwargs={"max_results": 7, "proxy_manager": None})
    kwargs = calls["kwargs"]
    assert kwargs["backend"] == "auto"
    assert kwargs["region"] == "us-en"
    assert kwargs["max_results"] == 7          # override wins
    assert kwargs["concurrency"] == 2
    assert kwargs["show_progress"] is False
    assert "cache" not in kwargs or kwargs.get("cache") is None


def test_run_watch_seen_history_is_bounded(monkeypatch):
    monkeypatch.setattr(watch, "MAX_SEEN", 3)
    add_watch("acme", dorks=["d1"])
    install_run_batch(monkeypatch, {"d1": results(
        "https://a.example/1", "https://a.example/2",
        "https://a.example/3", "https://a.example/4")})

    run_watch("acme")
    record = load_watch("acme")
    assert len(record["seen"]) == 3
    assert "https://a.example/1" not in record["seen"]


def test_run_watch_unknown_name():
    with pytest.raises(WatchError, match="not found"):
        run_watch("ghost")


def test_run_watch_notification_failure_is_swallowed(monkeypatch):
    add_watch("acme", dorks=["d1"], notify="discord:https://hook")
    install_run_batch(monkeypatch, {"d1": results("https://a.example/1")})

    def boom(target, message):
        raise RuntimeError("webhook down")

    monkeypatch.setattr(watch, "send_notification", boom)
    report = run_watch("acme")
    assert report["notified"] is False


def test_run_all_reports_errors(monkeypatch, tmp_path):
    add_watch("good", dorks=["d1"])
    add_watch("broken", dorks=[], batch_files=[str(tmp_path / "missing.txt")])
    install_run_batch(monkeypatch, {"d1": results("https://a.example/1")})
    console, _ = fake_console()

    reports, errors = run_all(console=console)
    assert [r["name"] for r in reports] == ["good"]
    assert len(errors) == 1 and errors[0][0] == "broken"


def test_max_seen_constant_is_bounded():
    assert MAX_SEEN == 10000


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def test_cli_add_list_show_remove(tmp_path, monkeypatch):
    import atdork

    console, buf = fake_console()
    monkeypatch.setattr(atdork, "console", console)

    assert atdork.watch_cli(["add", "acme", "--dork", "site:acme.com ext:env",
                             "--notify", "slack:https://hook",
                             "--max-results", "5"]) == 0
    assert "watch acme saved" in buf.getvalue()

    assert atdork.watch_cli(["list"]) == 0
    assert "acme" in buf.getvalue()

    assert atdork.watch_cli(["show", "acme"]) == 0
    text = buf.getvalue()
    assert "site:acme.com ext:env" in text
    assert "max_results=5" in text

    assert atdork.watch_cli(["remove", "acme"]) == 0
    assert list_watches() == []


def test_cli_add_requires_source():
    import atdork

    assert atdork.watch_cli(["add", "acme"]) == 1


def test_cli_no_args_shows_help():
    import atdork

    assert atdork.watch_cli([]) == 1


def test_cli_run_requires_name_or_all(monkeypatch):
    import atdork

    console, _ = fake_console()
    monkeypatch.setattr(atdork, "console", console)
    add_watch("acme", dorks=["d1"])
    assert atdork.watch_cli(["run"]) == 2


def test_cli_run_and_dry_run(monkeypatch):
    import atdork

    console, buf = fake_console()
    monkeypatch.setattr(atdork, "console", console)
    add_watch("acme", dorks=["d1"])

    assert atdork.watch_cli(["run", "acme", "--dry-run"]) == 0
    assert "dry run" in buf.getvalue()

    install_run_batch(monkeypatch, {"d1": results("https://a.example/1")})
    assert atdork.watch_cli(["run", "acme"]) == 0
    assert "baseline" in buf.getvalue()


def test_cli_run_all_some_failures(monkeypatch, tmp_path):
    import atdork

    console, _ = fake_console()
    monkeypatch.setattr(atdork, "console", console)
    add_watch("good", dorks=["d1"])
    add_watch("broken", dorks=[], batch_files=[str(tmp_path / "missing.txt")])
    install_run_batch(monkeypatch, {"d1": results("https://a.example/1")})

    assert atdork.watch_cli(["run", "--all"]) == 0


def test_cli_run_all_dork_failure_exit_code(monkeypatch):
    import atdork

    console, _ = fake_console()
    monkeypatch.setattr(atdork, "console", console)
    add_watch("acme", dorks=["d1"])
    install_run_batch(monkeypatch, {})          # every dork returns nothing

    assert atdork.watch_cli(["run", "acme"]) == 1
