"""Regression tests for the vulnerability-filter prefilter.

`filter_vulnerable` now uses a required-literal (Aho-Corasick) prefilter to
avoid evaluating every regex for every result. These tests pin down that the
optimization is invisible: the compiled regexes still decide every match.
"""

import random
import re

import pytest

from core.filter_vuln import filter_vulnerable, get_wordlist

_UNSAFE = re.compile(r"[\\\[\]()|*+?{}^$]")


def _combined(res):
    return f"{res.get('title', '')} {res.get('href', '')} {res.get('body', '')}"


def _bruteforce(results, patterns):
    return [res for res in results if any(p.search(_combined(res)) for p in patterns)]


def _planted_texts(patterns, count=250, seed=7):
    """Build texts that contain a real wordlist pattern (dots -> one char)."""
    rng = random.Random(seed)
    texts = []
    for pattern in rng.sample(patterns, min(count, len(patterns))):
        raw = pattern.pattern
        if _UNSAFE.search(raw):
            continue
        rendered = "".join(
            rng.choice("abcXYZ09-_") if ch == "." else ch for ch in raw
        )
        texts.append(f"prefix https://victim.example{rendered}?x=1 suffix")
    return texts


@pytest.mark.parametrize("name", ["wordpress", "joomla"])
def test_prefilter_is_equivalent_to_bruteforce(name):
    patterns = get_wordlist(name)
    texts = _planted_texts(patterns)
    assert texts, "test needs planted matches"
    results = [{"title": "", "href": text, "body": ""} for text in texts]

    actual = filter_vulnerable(results, filter_arg=name)[0]
    expected = _bruteforce(results, patterns)

    assert actual == expected
    assert len(actual) == len(texts), "every planted pattern must still be found"


def test_prefilter_keeps_non_matching_results_safe(tmp_path):
    (tmp_path / "mixed.txt").write_text(
        "admin.php\n"
        "/wp-(admin|content)/\n"
        "\\.git/\n"
        "ftp\\.example\\.com\n",
        encoding="utf-8",
    )
    cases = {
        "adminXphp": True,          # '.' is a regex wildcard
        "admin.php": True,
        "/wp-admin/x": True,        # alternation
        "/wp-content/y": True,
        "/wp-login/z": False,
        ".git/config": True,        # escaped dot is literal
        "xgit/config": False,
        "ftp.example.com": True,
        "ftpXexampleXcom": False,   # escaped dots are not wildcards
        "nothing here": False,
    }
    results = [{"title": "", "href": href, "body": ""} for href in cases]
    vulnerable, safe, filter_type = filter_vulnerable(
        results, filter_arg="mixed", wordlist_dir=str(tmp_path)
    )

    assert filter_type == "path"
    assert {r["href"] for r in vulnerable} == {h for h, v in cases.items() if v}
    assert {r["href"] for r in safe} == {h for h, v in cases.items() if not v}


def test_patterns_without_a_required_literal_still_work(tmp_path):
    (tmp_path / "dots-link.txt").write_text("...\n", encoding="utf-8")
    results = [
        {"title": "", "href": "ab", "body": ""},
        {"title": "", "href": "abc", "body": ""},
    ]
    vulnerable, safe, filter_type = filter_vulnerable(
        results, filter_arg="dots-link", wordlist_dir=str(tmp_path)
    )

    assert filter_type == "link"
    assert [r["href"] for r in vulnerable] == ["abc"]
    assert [r["href"] for r in safe] == ["ab"]


def test_link_mode_only_checks_href(tmp_path):
    (tmp_path / "only.txt").write_text("admin\n", encoding="utf-8")
    (tmp_path / "only-link.txt").write_text("admin\n", encoding="utf-8")
    result = {"title": "admin panel", "href": "https://example.com/", "body": "admin"}

    path_vuln, _, path_type = filter_vulnerable(
        [result], filter_arg="only", wordlist_dir=str(tmp_path)
    )
    link_vuln, _, link_type = filter_vulnerable(
        [result], filter_arg="only-link", wordlist_dir=str(tmp_path)
    )

    assert path_type == "path" and len(path_vuln) == 1
    assert link_type == "link" and link_vuln == []


def test_empty_inputs_keep_the_old_contract():
    assert filter_vulnerable([], filter_arg="wordpress") == ([], [], "unknown")
    assert filter_vulnerable("not-a-list", filter_arg="wordpress") == ([], [], "unknown")


def test_repeated_calls_reuse_cached_index(tmp_path):
    (tmp_path / "cached.txt").write_text("alpha\nbeta\n", encoding="utf-8")
    results = [{"title": "", "href": "alpha", "body": ""}]
    first = filter_vulnerable(results, filter_arg="cached", wordlist_dir=str(tmp_path))
    second = filter_vulnerable(results, filter_arg="cached", wordlist_dir=str(tmp_path))

    assert first[0] == second[0] == results
    assert first[2] == second[2] == "path"
