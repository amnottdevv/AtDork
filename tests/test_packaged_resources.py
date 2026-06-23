import pytest

from core.filter_vuln import filter_vulnerable, resolve_filter_arg


def test_filter_vulnerable_uses_packaged_wordlists_outside_repo_checkout(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    results = [{
        "title": "WordPress admin ajax",
        "href": "https://example.com/wp-admin/admin-ajax.php",
        "body": "ajax endpoint",
    }]

    vulnerable, safe, filter_type = filter_vulnerable(results, filter_arg="wordpress")

    assert vulnerable == results
    assert safe == []
    assert filter_type == "path"


def test_default_filter_resolution_uses_packaged_resources(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    _, _, location = resolve_filter_arg("wordpress")

    assert location.startswith("pkg://wordlists/")


def test_filter_vulnerable_raises_for_missing_wordlist(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    results = [{
        "title": "Anything",
        "href": "https://example.com",
        "body": "Anything",
    }]

    with pytest.raises(FileNotFoundError, match="does-not-exist.txt"):
        filter_vulnerable(results, filter_arg="does-not-exist")


def test_packaged_templates_work_outside_repo_checkout(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    pytest.importorskip("yaml")
    from core.template_dork import list_available_templates, load_template_dorks

    names = {template["name"] for template in list_available_templates()}
    assert "sqli" in names

    dorks = load_template_dorks("sqli")
    assert dorks
    assert all(isinstance(dork, str) for dork in dorks)
