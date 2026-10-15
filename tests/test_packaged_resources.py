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

def test_find_database_root_exists():
    root = find_database_root()
    # repo membawa folder database/ dengan 101 file
    assert root is not None


def test_list_database_dorks_returns_entries_with_counts():
    entries = list_database_dorks()
    assert len(entries) >= 1
    for e in entries:
        assert set(e) >= {"name", "relpath", "count"}
        assert e["relpath"].endswith(".txt")
        assert e["count"] >= 1  # file kosong tidak dihitung sebagai dork


def test_load_database_dorks_single_file():
    entries = list_database_dorks()
    # pakai file pertama yang terdaftar agar tidak hardcode nama
    first = entries[0]["relpath"]
    spec = first[:-4] if first.endswith(".txt") else first
    dorks = load_database_dorks(spec)
    assert dorks
    assert all(isinstance(d, str) and d.strip() for d in dorks)


def test_load_database_dorks_random_selection_is_reproducible():
    entries = list_database_dorks()
    spec = entries[0]["relpath"][:-4]
    a = load_database_dorks(spec, random_count=5, seed=42)
    b = load_database_dorks(spec, random_count=5, seed=42)
    assert a == b
    assert len(a) <= 5


def test_load_database_dorks_rejects_path_traversal():
    with pytest.raises(ValueError):
        load_database_dorks("../../etc/passwd")


def test_load_database_dorks_rejects_absolute_windows_path():
    with pytest.raises(ValueError):
        load_database_dorks("C:\\secrets\\dorks")


def test_load_database_dorks_rejects_unsupported_extension():
    with pytest.raises(ValueError):
        load_database_dorks("dorks.pdf")


def test_load_database_dorks_empty_spec():
    with pytest.raises(ValueError):
        load_database_dorks("   ")


def test_load_database_dorks_unknown_file():
    with pytest.raises(FileNotFoundError):
        load_database_dorks("file_yang_tidak_ada_12345")


def test_normalize_name_appends_txt():
    assert _normalize_name("01_footholds") == "01_footholds.txt"
    assert _normalize_name("/db-1/1_none") == "db-1/1_none.txt"
    assert _normalize_name("01_footholds.txt") == "01_footholds.txt"


def test_extract_database_to_tmp(tmp_path):
    dest = str(tmp_path / "dbout")
    out = extract_database(dest_dir=dest, overwrite=True)
    assert out == dest or out.endswith("dbout")
    # ekstrak ulang tanpa overwrite harus gagal
    with pytest.raises(FileExistsError):
        extract_database(dest_dir=dest, overwrite=False)


def test_extract_database_rejects_source_as_destination():
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
    assert "'wordpres.txt' tidak ditemukan" in str(exc.value)


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
