"""
Unit tests untuk resource ter-bundel: core.database_dork, core.template_dork,
dan core.filter_vuln.

Catatan: file ini dahulu berisi SALINAN kode modul-modul di atas (0 test —
tidak ada satupun `def test_`), sehingga resource ter-bundel praktis tak
teruji. Sekarang modul ASLINYA yang diuji.
"""

import pytest

from core.database_dork import (
    find_database_root,
    list_database_dorks,
    load_database_dorks,
    extract_database,
    _normalize_name,
)
from core.template_dork import list_available_templates, load_template_dorks
from core.filter_vuln import (
    resolve_filter_arg,
    filter_vulnerable,
    get_wordlist,
)


# ── core.database_dork ────────────────────────────────────────────────────
#
# Dork data lives in the Atdork-DB repository. Tests build a tiny fixture
# checkout and point ATDORK_DB_REPO at it so they are hermetic (CI does not
# have ~/Atdork-DB) and never touch the real package store.

@pytest.fixture()
def atdork_db(tmp_path, monkeypatch):
    """Minimal Atdork-DB checkout + clean CWD + isolated package store."""
    from core.package_manager import build_index

    repo = tmp_path / "Atdork-DB"
    (repo / "@cve").mkdir(parents=True)
    (repo / "@ghdb").mkdir()
    (repo / "@iot").mkdir()
    (repo / "@cve" / "cve_1.txt").write_text(
        "# header comment\nintext:\"cve-2025-\"\nintitle:test\n", encoding="utf-8"
    )
    (repo / "@ghdb" / "01_footholds.txt").write_text(
        "site:x.com\ndork two\ndork three\n", encoding="utf-8"
    )
    (repo / "@iot" / "camera.json").write_text('{"a": "intitle:cam"}', encoding="utf-8")
    build_index(repo=str(repo))

    monkeypatch.setenv("ATDORK_DB_REPO", str(repo))
    monkeypatch.setenv("ATDORK_PACKAGE_DIR", str(tmp_path / "store"))
    monkeypatch.chdir(tmp_path)  # no legacy ./database in the way
    return repo


def test_find_database_root_legacy_directory(tmp_path, monkeypatch):
    legacy = tmp_path / "database"
    legacy.mkdir()
    (legacy / "x.txt").write_text("dork\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert find_database_root() == str(legacy)


def test_find_database_root_missing_points_to_atdork_db(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError, match="Atdork-DB"):
        find_database_root()


def test_list_database_dorks_returns_entries_with_counts(atdork_db):
    entries = list_database_dorks()
    assert len(entries) >= 3
    for e in entries:
        assert set(e) >= {"name", "relpath", "count"}
        assert e["relpath"].startswith("@")          # package refs
        assert e["relpath"].endswith((".txt", ".csv", ".json"))
        assert e["count"] >= 1                        # empty files are not listed
    relpaths = {e["relpath"] for e in entries}
    assert "@cve/cve_1.txt" in relpaths
    assert "@iot/camera.json" in relpaths            # structured data is indexed


def test_load_database_dorks_single_file(atdork_db):
    dorks = load_database_dorks("@cve/cve_1")
    assert dorks == ['intext:"cve-2025-"', "intitle:test"]  # '#'-comments skipped
    assert all(isinstance(d, str) and d.strip() for d in dorks)


def test_load_database_dorks_bare_name_resolves_through_index(atdork_db):
    """Old-style specs like '01_footholds' keep working after the migration."""
    dorks = load_database_dorks("01_footholds")
    assert dorks == ["site:x.com", "dork two", "dork three"]


def test_load_database_dorks_prefers_installed_copy(atdork_db):
    from core.package_manager import install as install_package
    install_package("@ghdb/01_footholds")   # copy into the store
    dorks = load_database_dorks("@ghdb/01_footholds")
    assert "site:x.com" in dorks


def test_load_database_dorks_random_selection_is_reproducible(atdork_db):
    a = load_database_dorks("@ghdb/01_footholds", random_count=2, seed=42)
    b = load_database_dorks("@ghdb/01_footholds", random_count=2, seed=42)
    assert a == b
    assert len(a) <= 2


def test_load_database_dorks_folder_wide(atdork_db):
    """'@ghdb' loads every .txt member of the folder."""
    dorks = load_database_dorks("@ghdb")
    assert dorks == ["site:x.com", "dork two", "dork three"]


def test_load_database_dorks_folder_without_txt_members(atdork_db):
    """A folder holding only structured data (json/csv) is rejected clearly."""
    with pytest.raises(FileNotFoundError, match="loadable"):
        load_database_dorks("@iot")


def test_load_database_dorks_rejects_path_traversal(atdork_db):
    with pytest.raises(ValueError):
        load_database_dorks("../../etc/passwd")


def test_load_database_dorks_rejects_absolute_windows_path(atdork_db):
    with pytest.raises(ValueError):
        load_database_dorks("C:\\secrets\\dorks")


def test_load_database_dorks_rejects_unsupported_extension(atdork_db):
    with pytest.raises(ValueError):
        load_database_dorks("dorks.pdf")


def test_load_database_dorks_rejects_structured_json_ref(atdork_db):
    """csv/json packages are installable but not query-loadable."""
    with pytest.raises(ValueError, match="structured data"):
        load_database_dorks("@iot/camera.json")


def test_load_database_dorks_empty_spec(atdork_db):
    with pytest.raises(ValueError):
        load_database_dorks("   ")


def test_load_database_dorks_unknown_file(atdork_db):
    with pytest.raises(FileNotFoundError):
        load_database_dorks("file_yang_tidak_ada_12345")


def test_load_database_dorks_typo_suggests_close_match(atdork_db):
    with pytest.raises(FileNotFoundError) as exc:
        load_database_dorks("01_foothol")   # typo of 01_footholds
    assert "Did you mean" in str(exc.value)
    assert "@ghdb/01_footholds.txt" in str(exc.value)


def test_normalize_name_appends_txt():
    assert _normalize_name("01_footholds") == "01_footholds.txt"
    assert _normalize_name("/db-1/1_none") == "db-1/1_none.txt"
    assert _normalize_name("01_footholds.txt") == "01_footholds.txt"


def test_extract_database_from_legacy_copy(tmp_path, monkeypatch):
    """--extract-database still works when a legacy ./database exists."""
    legacy = tmp_path / "database"
    legacy.mkdir()
    (legacy / "x.txt").write_text("dork one\ndork two\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    dest = str(tmp_path / "dbout")
    out = extract_database(dest_dir=dest, overwrite=True)
    assert out == dest or out.endswith("dbout")
    assert (tmp_path / "dbout" / "x.txt").is_file()
    # re-extract without overwrite must fail
    with pytest.raises(FileExistsError):
        extract_database(dest_dir=dest, overwrite=False)


def test_extract_database_without_source_explains_atdork_db(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError, match="Atdork-DB"):
        extract_database(dest_dir=str(tmp_path / "dbout"), overwrite=True)


def test_extract_database_rejects_source_as_destination(tmp_path, monkeypatch):
    legacy = tmp_path / "database"
    legacy.mkdir()
    (legacy / "x.txt").write_text("dork\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        extract_database(dest_dir=find_database_root(), overwrite=False)


# ── core.template_dork ────────────────────────────────────────────────────

def test_list_available_templates():
    templates = list_available_templates()
    assert len(templates) >= 1
    for t in templates:
        assert "name" in t and "description" in t


def test_load_template_dorks_returns_dorks():
    templates = list_available_templates()
    dorks = load_template_dorks(templates[0]["name"])
    assert isinstance(dorks, list) and len(dorks) >= 1
    assert all(isinstance(d, str) for d in dorks)


def test_load_template_dorks_unknown_template():
    with pytest.raises(FileNotFoundError):
        load_template_dorks("template_tidak_ada_12345")


def test_load_template_dorks_select():
    templates = list_available_templates()
    all_dorks = load_template_dorks(templates[0]["name"])
    selected = load_template_dorks(templates[0]["name"], select="1")
    if len(all_dorks) >= 1:
        assert selected == [all_dorks[0]]


# ── core.filter_vuln ──────────────────────────────────────────────────────

def test_resolve_filter_arg_path_type():
    base, ftype, _ = resolve_filter_arg("wordpress")
    assert base == "wordpress"
    assert ftype == "path"


def test_resolve_filter_arg_link_type():
    """Suffix -link/-url menghasilkan tipe filter 'link' (dipakai filter_type)."""
    base, ftype, _ = resolve_filter_arg("joomla-link")
    assert base == "joomla"
    assert ftype == "link"


def test_resolve_filter_arg_unknown_gives_helpful_error():
    with pytest.raises(FileNotFoundError) as exc:
        resolve_filter_arg("wordpres")  # typo
    # pesan error menyebut file yang dicari + sumber yang dicek
    assert "'wordpres.txt' not found" in str(exc.value)


def test_filter_vulnerable_splits_results():
    results = [
        {"title": "wp admin", "href": "http://x.com/wp-login.php", "body": "WordPress"},
        {"title": "berita biasa", "href": "http://news.com/a", "body": "artikel"},
    ]
    vuln, safe, ftype = filter_vulnerable(results, filter_arg="wordpress")
    assert len(vuln) + len(safe) == len(results)
    assert ftype in ("path", "link")


def test_filter_vulnerable_unknown_wordlist():
    with pytest.raises(FileNotFoundError):
        filter_vulnerable([{"title": "a", "href": "http://a", "body": "b"}],
                          filter_arg="tidak_ada_wordlist")


def test_get_wordlist_unknown():
    with pytest.raises(FileNotFoundError):
        get_wordlist("juga_tidak_ada")
