"""
Unit tests for core.package_manager — the Atdork-DB package manager.

Every test runs against a tiny fixture repository wired through
ATDORK_DB_REPO / ATDORK_PACKAGE_DIR, so nothing here touches the real
~/Atdork-DB checkout or ~/.atdork/packages store.
"""

import hashlib
from pathlib import Path

import pytest

from core.package_manager import (
    AmbiguousRef,
    DBRepoNotFound,
    IndexNotFound,
    PackageError,
    RefError,
    RefNotFound,
    build_index,
    find_db_repo,
    get_package_dir,
    humanize,
    index_folders,
    install,
    is_installed,
    list_installed,
    load_index,
    parse_ref,
    read_index_header,
    resolve_batch_file,
    resolve_entry,
    resolve_folder,
    search,
    sha256_file,
    source_path,
    uninstall,
    update_repo,
    installed_path,
)


# ── fixture ───────────────────────────────────────────────────────────────

@pytest.fixture()
def repo(tmp_path, monkeypatch):
    """Two-folder Atdork-DB checkout with an index, plus isolated store."""
    root = tmp_path / "Atdork-DB"
    (root / "@cve").mkdir(parents=True)
    (root / "@cloud").mkdir()
    (root / "@cve" / "cve_1.txt").write_text(
        "# head\nintext:\"cve-2025-\"\nintitle:two\n", encoding="utf-8"
    )
    (root / "@cve" / "cve_2.txt").write_text("dork-a\ndork-b\n", encoding="utf-8")
    (root / "@cloud" / "aws.txt").write_text("site:aws.amazon.com\n", encoding="utf-8")
    (root / "@cve" / "shared.txt").write_text("shared cve\n", encoding="utf-8")
    (root / "@cloud" / "shared.txt").write_text("shared cloud\n", encoding="utf-8")
    build_index(repo=str(root))

    monkeypatch.setenv("ATDORK_DB_REPO", str(root))
    monkeypatch.setenv("ATDORK_PACKAGE_DIR", str(tmp_path / "store"))
    return root


def _store(monkeypatch, tmp_path) -> Path:
    monkeypatch.setenv("ATDORK_PACKAGE_DIR", str(tmp_path / "store"))
    return tmp_path / "store"


# ── ref parsing ───────────────────────────────────────────────────────────

def test_parse_ref_forms():
    canonical = parse_ref("@cve/cve_1.txt")
    assert (canonical.folder, canonical.name, canonical.exact_folder) == ("cve", "cve_1.txt", True)

    short = parse_ref("c@cve_1.txt")
    assert (short.folder, short.name, short.exact_folder) == ("c", "cve_1.txt", False)

    folder = parse_ref("@cve")
    assert (folder.folder, folder.name) == ("cve", None)

    bare = parse_ref("cve_1.txt")
    assert (bare.folder, bare.name) == (None, "cve_1.txt")


def test_parse_ref_rejects_empty():
    with pytest.raises(RefError):
        parse_ref("   ")
    with pytest.raises(RefError):
        parse_ref("@")          # '@' without a folder name
    with pytest.raises(RefError):
        parse_ref("@ cve/x")    # invalid folder name (space)


# ── resolution ────────────────────────────────────────────────────────────

def test_resolve_canonical_ref(repo):
    entry = resolve_entry("@cve/cve_1.txt")
    assert entry.ref == "@cve/cve_1.txt"
    assert entry.dork_lines == 2          # '#'-comment line not counted
    assert entry.folder == "cve"


def test_resolve_shorthand_disambiguates_by_file(repo):
    """The headline syntax: 'c@cve_1.txt' -> @cve/cve_1.txt even though
    both @cve and @cloud start with 'c'."""
    entry = resolve_entry("c@cve_1.txt")
    assert entry.ref == "@cve/cve_1.txt"


def test_resolve_bare_name_unique(repo):
    assert resolve_entry("aws.txt").ref == "@cloud/aws.txt"
    assert resolve_entry("aws").ref == "@cloud/aws.txt"      # auto .txt


def test_resolve_bare_name_ambiguous_lists_both(repo):
    with pytest.raises(AmbiguousRef) as exc:
        resolve_entry("shared.txt")
    assert set(exc.value.suggestions) == {"@cve/shared.txt", "@cloud/shared.txt"}


def test_resolve_unknown_folder_prefix_suggests_folders(repo):
    with pytest.raises(RefNotFound) as exc:
        resolve_entry("z@whatever.txt")
    assert "@cve" in exc.value.suggestions


def test_resolve_typo_suggests_close_file(repo):
    with pytest.raises(RefNotFound) as exc:
        resolve_entry("@cve/cve_1x.txt")
    assert any("cve_1.txt" in s for s in exc.value.suggestions)


def test_resolve_folder_only_ref_is_rejected(repo):
    with pytest.raises(RefError, match="whole folder"):
        resolve_entry("@cve")


def test_resolve_rejects_unsafe_reference(repo):
    with pytest.raises(RefError, match="Unsafe"):
        resolve_entry("@cve/../../etc/passwd")


def test_resolve_folder_exact_and_prefix(repo):
    assert resolve_folder("@cve") == "cve"
    assert resolve_folder("@cl") == "cloud"          # unique prefix
    with pytest.raises(AmbiguousRef):
        resolve_folder("@c")                          # cve + cloud
    with pytest.raises(RefNotFound):
        resolve_folder("@nope")


# ── install / uninstall / list ────────────────────────────────────────────

def test_install_creates_verified_copy(repo, tmp_path, monkeypatch):
    store = _store(monkeypatch, tmp_path)
    outcomes = install("c@cve_1.txt")
    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.status == "installed"
    dest = store / "cve" / "cve_1.txt"
    assert outcome.path == dest and dest.is_file()
    # checksum matches both the source file and the index entry
    expected = hashlib.sha256((repo / "@cve" / "cve_1.txt").read_bytes()).hexdigest()
    assert sha256_file(dest) == expected
    assert resolve_entry("@cve/cve_1.txt").sha256 == expected


def test_install_is_idempotent_and_force_updates(repo, tmp_path, monkeypatch):
    first = install("@cve/cve_1.txt")
    assert first[0].status == "installed"
    again = install("@cve/cve_1.txt")
    assert again[0].status == "exists"
    forced = install("@cve/cve_1.txt", force=True)
    assert forced[0].status == "updated"


def test_install_whole_folder(repo, tmp_path, monkeypatch):
    outcomes = install("@cve")
    assert len(outcomes) == 3
    assert {o.entry.name for o in outcomes} == {"cve_1.txt", "cve_2.txt", "shared.txt"}


def test_install_unknown_ref_raises(repo):
    with pytest.raises(PackageError):
        install("@cve/nope.txt")


def test_uninstall_removes_and_reports_missing(repo, tmp_path, monkeypatch):
    install("@cve/cve_1.txt")
    removed, missing = uninstall("@cve/cve_1.txt")
    assert [e.ref for e in removed] == ["@cve/cve_1.txt"]
    assert not missing
    assert not is_installed(resolve_entry("@cve/cve_1.txt"))

    removed, missing = uninstall("@cve/cve_1.txt")
    assert not removed and [e.ref for e in missing] == ["@cve/cve_1.txt"]


def test_list_installed_statuses(repo, tmp_path, monkeypatch):
    store = _store(monkeypatch, tmp_path)
    install("@cve/cve_1.txt")
    packages = list_installed()
    assert [(p.folder, p.name) for p in packages] == [("cve", "cve_1.txt")]
    assert packages[0].status == "ok"

    # tamper with the installed copy -> modified
    target = store / "cve" / "cve_1.txt"
    target.write_text(target.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
    assert list_installed()[0].status == "modified"

    # a file the index does not know about -> orphan
    ghost = store / "ghost" / "stray.txt"
    ghost.parent.mkdir(parents=True)
    ghost.write_text("stray\n", encoding="utf-8")
    statuses = {(p.folder, p.name): p.status for p in list_installed()}
    assert statuses[("ghost", "stray.txt")] == "orphan"


def test_list_installed_empty_store(tmp_path, monkeypatch):
    _store(monkeypatch, tmp_path)
    assert list_installed() == []


# ── batch file resolution ─────────────────────────────────────────────────

def test_resolve_batch_file_prefers_local_path(repo, tmp_path):
    local = tmp_path / "local_batch.txt"
    local.write_text("q1\n", encoding="utf-8")
    assert resolve_batch_file(str(local)) == local.resolve()


def test_resolve_batch_file_prefers_installed_copy(repo, tmp_path, monkeypatch):
    install("@cve/cve_1.txt")
    resolved = resolve_batch_file("c@cve_1.txt")
    store = get_package_dir()
    assert resolved == installed_path(resolve_entry("@cve/cve_1.txt"))
    assert str(resolved).startswith(str(store))


def test_resolve_batch_file_falls_back_to_repo(repo):
    resolved = resolve_batch_file("@cloud/aws.txt")
    assert resolved == repo / "@cloud" / "aws.txt"
    assert resolved.is_file()


def test_resolve_batch_file_unknown_raises(repo):
    with pytest.raises(RefError):
        resolve_batch_file("no-such-package.txt")


def test_resolve_batch_file_works_without_index(monkeypatch, tmp_path, repo):
    """Canonical refs still resolve from the store when the repo is gone."""
    from core import package_manager as pm

    install("@cve/cve_1.txt")
    monkeypatch.delenv("ATDORK_DB_REPO")
    monkeypatch.setattr(pm, "_search_paths", lambda explicit: [tmp_path / "missing-repo"])

    resolved = resolve_batch_file("@cve/cve_1.txt")
    assert resolved.is_file()
    assert str(resolved).startswith(str(tmp_path / "store"))


# ── discovery & errors ────────────────────────────────────────────────────

def test_find_db_repo_uses_env(repo):
    assert find_db_repo() == repo


def test_find_db_repo_not_found_mentions_clone(tmp_path, monkeypatch):
    from core import package_manager as pm

    monkeypatch.setattr(pm, "_search_paths", lambda explicit: [tmp_path / "nope"])
    with pytest.raises(DBRepoNotFound) as exc:
        find_db_repo()
    assert "Atdork-DB" in str(exc.value)
    assert "git clone" in str(exc.value)


def test_load_index_without_index_file(tmp_path, monkeypatch):
    empty = tmp_path / "bare-db"
    empty.mkdir()
    monkeypatch.setenv("ATDORK_DB_REPO", str(empty))
    with pytest.raises(IndexNotFound, match="index --build"):
        load_index()


def test_update_repo_without_git_says_so(repo):
    ok, message = update_repo()
    assert ok is False
    assert "not a git checkout" in message


# ── index build & search ──────────────────────────────────────────────────

def test_build_index_roundtrip(repo):
    stats = build_index()
    assert stats["entries"] == 5
    assert stats["folders"] == 2
    assert stats["total_dorks"] == 2 + 2 + 1 + 1 + 1   # comments not counted

    entries = load_index()
    by_ref = {e.ref: e for e in entries}
    entry = by_ref["@cve/cve_1.txt"]
    assert entry.sha256 == sha256_file(repo / "@cve" / "cve_1.txt")
    assert entry.size_bytes == (repo / "@cve" / "cve_1.txt").stat().st_size
    assert entry.dork_lines == 2
    assert entry.description == "CVE 1"
    assert set(index_folders(entries)) == {"cve", "cloud"}

    header = read_index_header()
    assert header["generated"]
    assert header["entries"] == "5"


def test_search_ranks_and_filters(repo):
    matches = search("cve")
    assert matches and all("cve" in m.ref for m in matches)
    assert search("aws cloud")            # description/folder tokens
    assert search("zzz-no-match") == []
    assert search("") == []


def test_humanize():
    assert humanize("Files-Containing-Passwords") == "Files Containing Passwords"
    assert humanize("01_footholds") == "01 Footholds"
    assert humanize("cve_1") == "CVE 1"
    assert humanize("600k-crypto-dorks-1") == "600k Crypto Dorks 1"


def test_source_path_includes_at_folder(repo):
    entry = resolve_entry("@cve/cve_1.txt")
    assert source_path(entry) == repo / "@cve" / "cve_1.txt"


# ── package_cli (atdork install / search / ...) ──────────────────────────

def test_package_cli_dispatch_unknown():
    from atdork import package_cli
    assert package_cli(["frobnicate"]) == 2


def test_package_cli_index_and_install_flow(repo, tmp_path, monkeypatch, capsys):
    from atdork import package_cli

    _store(monkeypatch, tmp_path)
    assert package_cli(["index"]) == 0
    assert package_cli(["index", "--build"]) == 0
    assert package_cli(["install", "c@cve_1.txt"]) == 0
    out = capsys.readouterr().out
    assert "@cve/cve_1.txt" in out and "installed" in out

    assert package_cli(["installed"]) == 0
    assert package_cli(["search", "cve"]) == 0
    assert package_cli(["search", "definitely-not-here"]) == 1
    assert package_cli(["uninstall", "c@cve_1.txt"]) == 0
    assert package_cli(["update"]) == 1        # fixture repo is not a git checkout


def test_package_cli_install_unknown_ref_fails(repo, capsys):
    from atdork import package_cli
    assert package_cli(["install", "@cve/missing.txt"]) == 1
    assert "Error" in capsys.readouterr().out
