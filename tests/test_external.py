"""
Unit tests for external plugin distribution (core/external.py): install from
a raw .py URL, from a git repository, from a third-party registry declared in
``plugins.sources``, and ``plugins publish``.

No network is used: ``file://`` URLs point at git repos / files created in
``tmp_path`` (git tests are skipped when git is unavailable).
"""

import io
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from rich.console import Console

from core.config import ConfigError, _CURRENT, _validate_layer
from core.external import (
    ExternalError,
    install_from_source,
    install_url,
    list_sources,
    looks_like_url,
    publish,
)
from core.package_manager import list_installed, uninstall

pytestmark = pytest.mark.skipif(shutil.which("git") is None,
                                reason="git executable not installed")


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """HOME + config layer never leak between tests."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("ATDORK_ENV", raising=False)
    monkeypatch.delenv("ATDORK_PACKAGE_DIR", raising=False)
    monkeypatch.delenv("ATDORK_DB_REPO", raising=False)
    _CURRENT.clear()
    yield
    _CURRENT.clear()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

PLUGIN_TEMPLATE = '''"""Test plugin."""
PLUGIN = {
    "name": "__NAME__",
    "version": "__VERSION__",
    "description": "__NAME__ tool",
    "options": [{"name": "text", "help": "Text"}],
}


def run(args, ctx):
    return 0
'''


def write_plugin(folder: Path, name="demo", version="1.0.0") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.py"
    path.write_text(PLUGIN_TEMPLATE.replace("__NAME__", name)
                    .replace("__VERSION__", version), encoding="utf-8")
    return path


def _git(repo: Path, *args: str, check: bool = True):
    return subprocess.run(["git", "-C", str(repo), *args],
                          check=check, capture_output=True, text=True)


def init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True,
                   capture_output=True, text=True)
    # Pin the initial branch name (works on every git version).
    subprocess.run(["git", "-C", str(path), "symbolic-ref", "HEAD",
                    "refs/heads/main"], check=True, capture_output=True, text=True)
    return path


def commit_all(repo: Path, message: str = "update") -> None:
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-qm", message, check=True)


def source_config(url: str, **overrides):
    spec = {"url": url}
    spec.update(overrides)
    return {"sources": {"demo": spec}}


def _layer(plugins_cfg):
    return {"version": 2, "plugins": plugins_cfg}


# --------------------------------------------------------------------------- #
# URL detection
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("spec", [
    "https://raw.githubusercontent.com/u/r/main/tool.py",
    "http://example.com/tool.py",
    "file:///tmp/repo",
    "ssh://git@host/repo.git",
    "git@github.com:user/repo.git",
])
def test_looks_like_url_yes(spec):
    assert looks_like_url(spec)


@pytest.mark.parametrize("spec", [
    "@plugins/dorkbuilder", "c@cve_1.txt", "cve_1.txt", "", "@cve",
])
def test_looks_like_url_no(spec):
    assert not looks_like_url(spec)


# --------------------------------------------------------------------------- #
# Raw .py URL
# --------------------------------------------------------------------------- #

def test_install_raw_py_url(tmp_path):
    module = write_plugin(tmp_path / "src", name="hello")
    store = tmp_path / "store"
    outcomes = install_url(f"file://{module}", package_dir=str(store))

    assert [o.status for o in outcomes] == ["installed"]
    dest = store / "plugins" / "hello" / "hello.py"
    assert dest.is_file()
    assert outcomes[0].entry.ref == "@plugins/hello/hello.py"
    # the tool name comes from PLUGIN metadata, not the URL
    assert outcomes[0].entry.dork_lines == 0


def test_install_raw_py_url_oversize(tmp_path, monkeypatch):
    module = write_plugin(tmp_path / "src", name="big")
    monkeypatch.setattr("core.external.MAX_FILE_BYTES", 32)
    with pytest.raises(ExternalError, match="larger than"):
        install_url(f"file://{module}", package_dir=str(tmp_path / "store"))


def test_install_raw_py_url_rejects_fragment(tmp_path):
    module = write_plugin(tmp_path / "src", name="hello")
    with pytest.raises(ExternalError, match="only applies to repository URLs"):
        install_url(f"file://{module}#sub", package_dir=str(tmp_path / "store"))


def test_install_raw_py_url_invalid_meta(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "bad.py").write_text('PLUGIN = {"name": "Bad"}\n', encoding="utf-8")
    with pytest.raises(ExternalError, match="invalid plugin metadata"):
        install_url(f"file://{src / 'bad.py'}", package_dir=str(tmp_path / "store"))


def test_install_raw_py_url_helper_without_meta(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "plain.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(ExternalError, match="PLUGIN"):
        install_url(f"file://{src / 'plain.py'}", package_dir=str(tmp_path / "store"))


# --------------------------------------------------------------------------- #
# Git repositories
# --------------------------------------------------------------------------- #

def test_install_repo_single_plugin(tmp_path):
    repo = init_repo(tmp_path / "repo")
    write_plugin(repo / "tool", name="solo")
    commit_all(repo)

    store = tmp_path / "store"
    outcomes = install_url(f"file://{repo}", package_dir=str(store))
    assert (store / "plugins" / "solo" / "solo.py").is_file()
    assert outcomes[0].status == "installed"


def test_install_repo_subpath_selects_tool(tmp_path):
    repo = init_repo(tmp_path / "repo")
    write_plugin(repo / "alpha", name="alpha")
    write_plugin(repo / "beta", name="beta")
    commit_all(repo)

    store = tmp_path / "store"
    install_url(f"file://{repo}#beta", package_dir=str(store))
    assert (store / "plugins" / "beta" / "beta.py").is_file()
    assert not (store / "plugins" / "alpha").exists()


def test_install_repo_subpath_can_be_a_file(tmp_path):
    repo = init_repo(tmp_path / "repo")
    write_plugin(repo / "beta", name="beta")
    commit_all(repo)

    store = tmp_path / "store"
    install_url(f"file://{repo}#beta/beta.py", package_dir=str(store))
    assert (store / "plugins" / "beta" / "beta.py").is_file()


def test_install_repo_ambiguous_needs_subpath(tmp_path):
    repo = init_repo(tmp_path / "repo")
    write_plugin(repo / "alpha", name="alpha")
    write_plugin(repo / "beta", name="beta")
    commit_all(repo)

    with pytest.raises(ExternalError, match="contains 2 plugins"):
        install_url(f"file://{repo}", package_dir=str(tmp_path / "store"))


def test_install_repo_without_plugins(tmp_path):
    repo = init_repo(tmp_path / "repo")
    (repo / "README.md").write_text("# nothing here\n", encoding="utf-8")
    commit_all(repo)

    with pytest.raises(ExternalError, match="no installable plugin found"):
        install_url(f"file://{repo}", package_dir=str(tmp_path / "store"))


def test_install_repo_invalid_meta_reported(tmp_path):
    repo = init_repo(tmp_path / "repo")
    tool = repo / "broken"
    tool.mkdir(parents=True)
    (tool / "broken.py").write_text('PLUGIN = {"name": "Bad Name"}\n',
                                    encoding="utf-8")
    commit_all(repo)

    with pytest.raises(ExternalError, match="invalid plugin metadata"):
        install_url(f"file://{repo}", package_dir=str(tmp_path / "store"))


def test_install_repo_git_ref_pins_branch(tmp_path):
    repo = init_repo(tmp_path / "repo")
    write_plugin(repo / "tool", name="tool", version="1.0.0")
    commit_all(repo, "v1")
    _git(repo, "checkout", "-q", "-b", "release")
    write_plugin(repo / "tool", name="tool", version="9.9.9")
    commit_all(repo, "v2")
    _git(repo, "checkout", "-q", "main")

    store = tmp_path / "store"
    install_url(f"file://{repo}", git_ref="release", package_dir=str(store))
    installed = (store / "plugins" / "tool" / "tool.py").read_text(encoding="utf-8")
    assert "9.9.9" in installed


def test_install_repo_subpath_escape_rejected(tmp_path):
    repo = init_repo(tmp_path / "repo")
    write_plugin(repo / "tool", name="tool")
    commit_all(repo)

    with pytest.raises(ExternalError, match="escapes the repository"):
        install_url(f"file://{repo}#../outside", package_dir=str(tmp_path / "store"))


# --------------------------------------------------------------------------- #
# Third-party sources (plugins.sources)
# --------------------------------------------------------------------------- #

def build_registry(root: Path) -> Path:
    """A minimal registry repo: @plugins/tool/tool.py + published Index.idn."""
    repo = init_repo(root)
    write_plugin(repo / "@plugins" / "tool", name="tool")
    commit_all(repo, "tool")
    publish("@plugins/tool", repo=str(repo), write=True)
    commit_all(repo, "index")
    return repo


def test_list_sources_reads_mapping():
    cfg = source_config("https://example.com/x.git", ref="main", index="Idx")
    assert list_sources(cfg) == {"demo": {
        "url": "https://example.com/x.git", "ref": "main", "index": "Idx"}}
    assert list_sources({}) == {}
    assert list_sources({"sources": {"bad": "not-a-dict"}}) == {}


def test_install_from_source(tmp_path):
    repo = build_registry(tmp_path / "registry")
    store = tmp_path / "store"
    workspace = SimpleNamespace(root=str(tmp_path / "env"))

    outcomes = install_from_source(
        "demo", "@plugins/tool", config=source_config(f"file://{repo}"),
        workspace=workspace, package_dir=str(store))

    assert [o.status for o in outcomes] == ["installed"]
    assert (store / "plugins" / "tool" / "tool.py").is_file()
    # the checkout is cached inside the workspace
    assert (tmp_path / "env" / "cache" / "sources" / "demo" / ".git").is_dir()


def test_install_from_source_checksum_mismatch(tmp_path):
    repo = build_registry(tmp_path / "registry")
    store = tmp_path / "store"
    workspace = SimpleNamespace(root=str(tmp_path / "env"))
    cfg = source_config(f"file://{repo}")

    first = install_from_source("demo", "@plugins/tool", config=cfg,
                                workspace=workspace, package_dir=str(store))
    assert first[0].status == "installed"

    cached = tmp_path / "env" / "cache" / "sources" / "demo"
    (cached / "@plugins" / "tool" / "tool.py").write_text(
        "# tampered\n" + (cached / "@plugins" / "tool" / "tool.py").read_text(),
        encoding="utf-8")
    with pytest.raises(ExternalError, match="checksum mismatch"):
        install_from_source("demo", "@plugins/tool", config=cfg,
                            workspace=workspace, package_dir=str(store),
                            force=True)


def test_install_from_source_unknown(tmp_path):
    with pytest.raises(ExternalError, match="unknown plugin source 'nope'"):
        install_from_source("nope", "@plugins/tool",
                            config=source_config("file:///nowhere"),
                            package_dir=str(tmp_path / "store"))


def test_install_from_source_missing_index(tmp_path):
    repo = init_repo(tmp_path / "registry")
    write_plugin(repo / "@plugins" / "tool", name="tool")
    commit_all(repo)

    with pytest.raises(ExternalError, match="Index.idn not found"):
        install_from_source("demo", "@plugins/tool",
                            config=source_config(f"file://{repo}"),
                            workspace=SimpleNamespace(root=str(tmp_path / "env")),
                            package_dir=str(tmp_path / "store"))


def test_install_from_source_missing_file(tmp_path):
    repo = build_registry(tmp_path / "registry")
    (repo / "@plugins" / "tool" / "tool.py").unlink()
    commit_all(repo, "drop file")
    with pytest.raises(ExternalError, match="missing from the checkout"):
        install_from_source("demo", "@plugins/tool",
                            config=source_config(f"file://{repo}"),
                            workspace=SimpleNamespace(root=str(tmp_path / "env")),
                            package_dir=str(tmp_path / "store"))


# --------------------------------------------------------------------------- #
# publish
# --------------------------------------------------------------------------- #

def test_publish_prints_index_lines(tmp_path):
    repo = init_repo(tmp_path / "repo")
    write_plugin(repo / "@plugins" / "tool", name="tool")

    lines, written = publish("@plugins/tool", repo=str(repo))
    assert written is None
    assert len(lines) == 1
    fields = lines[0].split("|")
    assert fields[0] == "@plugins/tool/tool.py"
    assert fields[3] == "0"
    assert fields[4] == "tool tool"
    assert len(fields[1]) == 64  # sha256


def test_publish_write_creates_index(tmp_path):
    repo = init_repo(tmp_path / "repo")
    write_plugin(repo / "@plugins" / "tool", name="tool")

    lines, written = publish("@plugins/tool", repo=str(repo), write=True)
    assert written == repo / "Index.idn"
    text = written.read_text(encoding="utf-8")
    assert text.splitlines()[0].startswith("# Atdork-DB index")
    assert "# entries: 1" in text
    assert lines[0] in text


def test_publish_write_preserves_other_entries(tmp_path):
    repo = init_repo(tmp_path / "repo")
    write_plugin(repo / "@plugins" / "tool", name="tool")
    index = repo / "Index.idn"
    index.write_text(
        "# my registry v1\n"
        "@cve/cve_1.txt|abc|10|3|CVE dorks\n"
        "@plugins/tool/stale.py|old|1|0|stale\n",
        encoding="utf-8")

    publish("@plugins/tool", repo=str(repo), write=True)
    rows = [ln for ln in index.read_text(encoding="utf-8").splitlines()
            if ln and not ln.startswith("#")]
    assert "@cve/cve_1.txt|abc|10|3|CVE dorks" in rows
    assert not any(r.startswith("@plugins/tool/stale.py") for r in rows)
    assert any(r.startswith("@plugins/tool/tool.py|") for r in rows)
    assert "# my registry v1" in index.read_text(encoding="utf-8")
    assert "# total-dorks: 3" in index.read_text(encoding="utf-8")


def test_publish_rejects_non_plugin_ref(tmp_path):
    repo = init_repo(tmp_path / "repo")
    with pytest.raises(ExternalError, match="expects a plugin tool folder"):
        publish("@cve/cve_1.txt", repo=str(repo))


def test_publish_missing_tool(tmp_path):
    repo = init_repo(tmp_path / "repo")
    with pytest.raises(ExternalError, match="not found"):
        publish("@plugins/ghost", repo=str(repo),
                package_dir=str(tmp_path / "store"))


# --------------------------------------------------------------------------- #
# Store integration: listing + uninstall fallback
# --------------------------------------------------------------------------- #

def test_installed_marks_external_status(tmp_path):
    module = write_plugin(tmp_path / "src", name="hello")
    store = tmp_path / "store"
    install_url(f"file://{module}", package_dir=str(store))

    packages = list_installed(package_dir=str(store))
    assert [(p.folder, p.name, p.status) for p in packages] == [
        ("plugins", "hello/hello.py", "external")]


def test_uninstall_external_plugin_fallback(tmp_path):
    module = write_plugin(tmp_path / "src", name="hello")
    store = tmp_path / "store"
    install_url(f"file://{module}", package_dir=str(store))

    removed, missing = uninstall("@plugins/hello", package_dir=str(store))
    assert [e.ref for e in removed] == ["@plugins/hello/hello.py"]
    assert not missing
    assert not (store / "plugins" / "hello").exists()


def test_uninstall_unknown_external_ref(tmp_path):
    store = tmp_path / "store"
    from core.package_manager import PackageError
    with pytest.raises(PackageError):
        uninstall("@plugins/ghost", package_dir=str(store))


# --------------------------------------------------------------------------- #
# Config validation (plugins.sources)
# --------------------------------------------------------------------------- #

def test_config_sources_valid():
    _validate_layer(_layer({"sources": {
        "mine": {"url": "https://x/y.git", "ref": "main", "index": "Index.idn"},
    }}), "test")


@pytest.mark.parametrize("sources, match", [
    ("not-a-mapping", "must be a mapping"),
    ({"bad name": {"url": "u"}}, "source names must match"),
    ({"mine": "nope"}, "must be a mapping"),
    ({"mine": {"urll": "u"}}, "unknown key"),
    ({"mine": {}}, "url must be a non-empty string"),
    ({"mine": {"url": "u", "ref": 3}}, "ref must be a non-empty string"),
])
def test_config_sources_invalid(sources, match):
    with pytest.raises(ConfigError, match=match):
        _validate_layer(_layer({"sources": sources}), "test")


# --------------------------------------------------------------------------- #
# CLI smoke (install dispatch + plugins publish/sources)
# --------------------------------------------------------------------------- #

def fake_console():
    buf = io.StringIO()
    return Console(file=buf, width=200), buf


def test_cli_install_url_and_plugins_cli(tmp_path, monkeypatch):
    import atdork

    module = write_plugin(tmp_path / "src", name="hello")
    store = tmp_path / "store"
    monkeypatch.setattr(atdork, "get_package_store_hint",
                        lambda: str(store))
    monkeypatch.setattr("core.package_manager.get_package_dir",
                        lambda explicit=None: store)
    monkeypatch.setattr("core.external.get_package_dir",
                        lambda explicit=None: store)
    console, _ = fake_console()
    monkeypatch.setattr(atdork, "console", console)

    assert atdork.package_cli(["install", f"file://{module}"]) == 0
    assert (store / "plugins" / "hello" / "hello.py").is_file()

    assert atdork.plugins_cli(["list"]) == 0
    assert atdork.plugins_cli(["sources"]) == 0


def test_cli_plugins_publish(tmp_path, monkeypatch):
    import atdork

    repo = init_repo(tmp_path / "repo")
    write_plugin(repo / "@plugins" / "tool", name="tool")
    console, buf = fake_console()
    monkeypatch.setattr(atdork, "console", console)

    assert atdork.plugins_cli(["publish", "@plugins/tool",
                               "--repo", str(repo)]) == 0
    assert "@plugins/tool/tool.py" in buf.getvalue()

    assert atdork.plugins_cli(["publish", "@plugins/tool",
                               "--repo", str(repo), "--write"]) == 0
    assert (repo / "Index.idn").is_file()
