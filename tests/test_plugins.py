"""
Unit tests for the plugin system (core/plugins.py), its package-manager
integration (.py packages under @plugins) and the CLI wiring
(atdork.plugins_cli, plugin flag registration/dispatch).

Network is never touched: plugins are local files, discovery reads the
AST literal PLUGIN dict, and execution is importlib on tmp files. HOME is
patched so ~/.atdork never leaks outside tmp_path.
"""

import argparse
import io
from pathlib import Path

import pytest
from rich.console import Console

import core.plugins as pl
from core.config import ConfigError, _CURRENT, _validate_layer, override_setting
from core.database_dork import _resolve_dork_file
from core.env import create_env
from core.package_manager import (
    PackageError,
    build_index,
    install,
    list_installed,
    load_index,
    resolve_batch_file,
    uninstall,
)
from core.plugins import (
    PluginDef,
    PluginError,
    discover_plugins,
    dispatch_plugin,
    load_plugin_meta,
    make_context,
    register_plugin_args,
    register_warnings,
    run_plugin,
    triggered_plugins,
    validate_meta,
)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Config layer + HOME never leak between tests."""
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

def meta(name="demo", **overrides):
    """Minimal valid PLUGIN metadata."""
    value = {
        "name": name,
        "version": "1.0.0",
        "description": "Demo plugin",
        "options": [{"name": "text", "help": "Text option"}],
    }
    value.update(overrides)
    return value


def plugin_source(meta_value=None, body="    return 0"):
    """Full plugin file contents: PLUGIN literal + run() entry point."""
    return f"PLUGIN = {meta_value if meta_value is not None else meta()!r}\n\n\n" \
           f"def run(args, ctx):\n{body}\n"


def write_plugin(folder: Path, source: str, filename="demo.py") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    path.write_text(source, encoding="utf-8")
    return path


def use_paths(monkeypatch, *dirs, extra=None):
    """Point plugins discovery at local folders via the config layer."""
    cfg = {"paths": [str(d) for d in dirs]}
    if extra:
        cfg.update(extra)
    override_setting("plugins", cfg)


def fake_console():
    buf = io.StringIO()
    return Console(file=buf, width=100), buf


# --------------------------------------------------------------------------- #
# Metadata: AST literal parsing + contract validation
# --------------------------------------------------------------------------- #

def test_load_meta_valid(tmp_path):
    path = write_plugin(tmp_path, plugin_source(meta()), "ok.py")
    assert load_plugin_meta(path)["name"] == "demo"


def test_load_meta_missing_plugin(tmp_path):
    path = tmp_path / "plain.py"
    path.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(PluginError, match="PLUGIN"):
        load_plugin_meta(path)


def test_load_meta_non_literal_rejected(tmp_path):
    # Code would run at import time — the loader must refuse anything that
    # is not a literal (this is the no-execution security property).
    path = tmp_path / "evil.py"
    path.write_text(
        "PLUGIN = dict(name=open('/etc/passwd').read())\n", encoding="utf-8"
    )
    with pytest.raises(PluginError, match="literal"):
        load_plugin_meta(path)


def test_load_meta_syntax_error(tmp_path):
    path = tmp_path / "broken.py"
    path.write_text("PLUGIN = {oops\n", encoding="utf-8")
    with pytest.raises(PluginError, match="syntax error"):
        load_plugin_meta(path)


def test_load_meta_not_a_dict(tmp_path):
    path = tmp_path / "list.py"
    path.write_text("PLUGIN = ['a']\n", encoding="utf-8")
    with pytest.raises(PluginError, match="dict"):
        load_plugin_meta(path)


def test_validate_meta_ok():
    assert validate_meta(meta(), "demo.py") == []


def test_validate_meta_bad_name():
    errors = validate_meta(meta(name="Demo Plugin"), "demo.py")
    assert any("name" in e for e in errors)


def test_validate_meta_unknown_key():
    errors = validate_meta(meta(extra="x"), "demo.py")
    assert any("unknown key" in e for e in errors)


def test_validate_meta_option_bad_name():
    m = meta(options=[{"name": "--other-text"}])  # wrong prefix form
    errors = validate_meta(m, "demo.py")
    assert any("--<plugin>-<name>" in e for e in errors)


def test_validate_meta_option_duplicate():
    m = meta(options=[{"name": "text"}, {"name": "text"}])
    assert any("duplicate" in e for e in validate_meta(m, "demo.py"))


def test_validate_meta_option_bad_type():
    m = meta(options=[{"name": "text", "type": "path"}])
    assert any("type must be" in e for e in validate_meta(m, "demo.py"))


def test_validate_meta_store_true_conflicts():
    m = meta(options=[{"name": "v", "action": "store_true", "choices": ["a"]}])
    assert any("store_true" in e for e in validate_meta(m, "demo.py"))


def test_validate_meta_options_not_list():
    m = meta(options={"name": "text"})
    assert any("must be a list" in e for e in validate_meta(m, "demo.py"))


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #

def test_discover_from_local_path(tmp_path, monkeypatch):
    write_plugin(tmp_path / "tools", plugin_source())
    use_paths(monkeypatch, tmp_path / "tools")
    defs = discover_plugins()
    assert [d.name for d in defs] == ["demo"]
    assert defs[0].source != "store"
    assert defs[0].options[0]["name"] == "text"


def test_discover_skips_helpers_and_conftest(tmp_path, monkeypatch):
    write_plugin(tmp_path / "tools", plugin_source())
    (tmp_path / "tools" / "_helper.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "tools" / "conftest.py").write_text("Y = 2\n", encoding="utf-8")
    use_paths(monkeypatch, tmp_path / "tools")
    assert [d.name for d in discover_plugins()] == ["demo"]


def test_discover_invalid_meta_recorded(tmp_path, monkeypatch):
    write_plugin(tmp_path / "tools", plugin_source(meta(name="BAD NAME")))
    use_paths(monkeypatch, tmp_path / "tools")
    defs = discover_plugins()
    assert len(defs) == 1
    assert defs[0].error  # surfaced as invalid, not silently dropped


def test_discover_store(tmp_path, monkeypatch):
    store = tmp_path / "store"
    write_plugin(store / "plugins", plugin_source())
    monkeypatch.setenv("ATDORK_PACKAGE_DIR", str(store))
    defs = discover_plugins()
    assert [d.name for d in defs] == ["demo"]
    assert defs[0].source == "store"


def test_discover_local_overrides_store(tmp_path, monkeypatch):
    store = tmp_path / "store"
    write_plugin(store / "plugins", plugin_source(meta(version="store")))
    local = tmp_path / "dev"
    write_plugin(local, plugin_source(meta(version="local")))
    monkeypatch.setenv("ATDORK_PACKAGE_DIR", str(store))
    use_paths(monkeypatch, local)
    defs = discover_plugins()
    assert len(defs) == 1
    assert defs[0].version == "local"


def test_discover_disabled_list(tmp_path, monkeypatch):
    write_plugin(tmp_path / "tools", plugin_source())
    use_paths(monkeypatch, tmp_path / "tools", extra={"disabled": ["demo"]})
    assert discover_plugins()[0].enabled is False


def test_discover_enabled_allowlist(tmp_path, monkeypatch):
    write_plugin(tmp_path / "tools", plugin_source())
    write_plugin(tmp_path / "tools", plugin_source(meta(name="other")), "other.py")
    use_paths(monkeypatch, tmp_path / "tools", extra={"enabled": ["other"]})
    status = {d.name: d.enabled for d in discover_plugins()}
    assert status == {"demo": False, "other": True}


def test_discover_enabled_auto_enables_all(tmp_path, monkeypatch):
    write_plugin(tmp_path / "tools", plugin_source())
    use_paths(monkeypatch, tmp_path / "tools", extra={"enabled": "auto"})
    assert discover_plugins()[0].enabled is True


def test_register_warnings_prefix_ambiguity():
    a = PluginDef("demo", "1", "", [], Path("a.py"), "store")
    b = PluginDef("demo-x", "1", "", [], Path("b.py"), "store")
    warnings = register_warnings([a, b])
    assert any("flag-prefix" in w for w in warnings)


# --------------------------------------------------------------------------- #
# Argument registration (mandatory --<plugin>-<option> format)
# --------------------------------------------------------------------------- #

def test_register_flags_and_dests(tmp_path, monkeypatch):
    write_plugin(tmp_path / "tools", plugin_source())
    use_paths(monkeypatch, tmp_path / "tools")
    parser = argparse.ArgumentParser()
    defs = register_plugin_args(parser)
    assert [d.name for d in defs] == ["demo"]
    args = parser.parse_args(["--demo", "--demo-text", "hello"])
    assert args.demo is True
    assert args.demo_text == "hello"


def test_register_option_name_with_dashes(tmp_path, monkeypatch):
    m = meta(options=[{"name": "func-lain", "help": "Multi-dash option"}])
    write_plugin(tmp_path / "tools", plugin_source(m))
    use_paths(monkeypatch, tmp_path / "tools")
    parser = argparse.ArgumentParser()
    register_plugin_args(parser)
    args = parser.parse_args(["--demo-func-lain", "x"])
    assert args.demo_func_lain == "x"


def test_register_switch_action(tmp_path, monkeypatch):
    m = meta(options=[{"name": "verbose", "action": "store_true"}])
    write_plugin(tmp_path / "tools", plugin_source(m))
    use_paths(monkeypatch, tmp_path / "tools")
    parser = argparse.ArgumentParser()
    register_plugin_args(parser)
    assert parser.parse_args(["--demo-verbose"]).demo_verbose is True
    assert parser.parse_args([]).demo_verbose is False


def test_register_choices_and_int(tmp_path, monkeypatch):
    m = meta(options=[
        {"name": "kind", "choices": ["a", "b"], "default": "a"},
        {"name": "limit", "type": "int", "default": 5},
    ])
    write_plugin(tmp_path / "tools", plugin_source(m))
    use_paths(monkeypatch, tmp_path / "tools")
    parser = argparse.ArgumentParser()
    register_plugin_args(parser)
    args = parser.parse_args(["--demo-kind", "b", "--demo-limit", "9"])
    assert args.demo_kind == "b" and args.demo_limit == 9
    assert parser.parse_args([]).demo_limit == 5
    with pytest.raises(SystemExit):
        parser.parse_args(["--demo-kind", "zzz"])


def test_register_config_option_defaults(tmp_path, monkeypatch):
    write_plugin(tmp_path / "tools", plugin_source())
    use_paths(monkeypatch, tmp_path / "tools",
              extra={"options": {"demo": {"text": "from-config"}}})
    parser = argparse.ArgumentParser()
    register_plugin_args(parser)
    assert parser.parse_args([]).demo_text == "from-config"
    # CLI still wins over the configured default.
    assert parser.parse_args(["--demo-text", "cli"]).demo_text == "cli"


def test_register_collision_with_core_flag_warns(tmp_path, monkeypatch):
    # Plugin named "query": the bare trigger collides with the core --query,
    # but the prefixed options stay available (implicit trigger path).
    m = meta(name="query", options=[{"name": "text"}])
    write_plugin(tmp_path / "tools", plugin_source(m), "query.py")
    use_paths(monkeypatch, tmp_path / "tools")
    from atdork import build_parser
    warnings = []
    parser = argparse.ArgumentParser()
    parser.add_argument("-q", "--query", dest="query")
    register_plugin_args(parser, warn=warnings.append)
    assert any("collides" in w for w in warnings)
    args = parser.parse_args(["--query-text", "x"])
    assert args.query_text == "x"
    assert args.query is None   # core flag untouched


def test_register_invalid_plugin_skipped_with_warning(tmp_path, monkeypatch):
    write_plugin(tmp_path / "tools", plugin_source(meta(name="BAD")))
    use_paths(monkeypatch, tmp_path / "tools")
    warnings = []
    defs = register_plugin_args(argparse.ArgumentParser(), warn=warnings.append)
    assert defs == []
    assert any("ignored" in w for w in warnings)


def test_build_parser_registers_store_plugins(tmp_path, monkeypatch):
    store = tmp_path / "store"
    write_plugin(store / "plugins", plugin_source())
    monkeypatch.setenv("ATDORK_PACKAGE_DIR", str(store))
    from atdork import build_parser
    args = build_parser().parse_args(["--demo", "--demo-text", "x"])
    assert args.demo is True and args.demo_text == "x"


# --------------------------------------------------------------------------- #
# Trigger detection & dispatch
# --------------------------------------------------------------------------- #

def test_triggered_implicit_by_prefixed_flag(tmp_path, monkeypatch):
    write_plugin(tmp_path / "tools", plugin_source())
    use_paths(monkeypatch, tmp_path / "tools")
    defs = discover_plugins()
    got = triggered_plugins(defs, ["--demo-text", "x"])
    assert [d.name for d in got] == ["demo"]


def test_triggered_bare_flag(tmp_path, monkeypatch):
    write_plugin(tmp_path / "tools", plugin_source())
    use_paths(monkeypatch, tmp_path / "tools")
    defs = discover_plugins()
    args = argparse.Namespace(demo=True)
    assert [d.name for d in triggered_plugins(defs, [], args)] == ["demo"]


def test_not_triggered_without_cli_flags(tmp_path, monkeypatch):
    # Config option defaults alone must never launch a plugin.
    write_plugin(tmp_path / "tools", plugin_source())
    use_paths(monkeypatch, tmp_path / "tools",
              extra={"options": {"demo": {"text": "cfg"}}})
    defs = discover_plugins()
    args = argparse.Namespace(demo=False, demo_text="cfg")
    assert triggered_plugins(defs, ["-q", "x"], args) == []


def test_dispatch_none_when_not_triggered(tmp_path, monkeypatch):
    write_plugin(tmp_path / "tools", plugin_source())
    use_paths(monkeypatch, tmp_path / "tools")
    args = argparse.Namespace(demo=False, demo_text=None)
    assert dispatch_plugin(args, ["-q", "x"]) is None


def test_dispatch_runs_plugin(tmp_path, monkeypatch):
    marker = tmp_path / "marker.txt"
    body = f"    from pathlib import Path\n" \
           f"    Path({str(marker)!r}).write_text('ran')\n    return 0"
    write_plugin(tmp_path / "tools", plugin_source(body=body))
    use_paths(monkeypatch, tmp_path / "tools")
    args = argparse.Namespace(demo=False, demo_text="x")
    rc = dispatch_plugin(args, ["--demo-text", "x"])
    assert rc == 0
    assert marker.read_text() == "ran"


def test_dispatch_propagates_nonzero_exit(tmp_path, monkeypatch):
    write_plugin(tmp_path / "tools", plugin_source(body="    return 3"))
    use_paths(monkeypatch, tmp_path / "tools")
    args = argparse.Namespace(demo=True, demo_text=None)
    assert dispatch_plugin(args, ["--demo"]) == 3


def test_dispatch_plugin_crash_becomes_error(tmp_path, monkeypatch):
    write_plugin(tmp_path / "tools",
                 plugin_source(body="    raise RuntimeError('boom')"))
    use_paths(monkeypatch, tmp_path / "tools")
    console, buf = fake_console()
    args = argparse.Namespace(demo=True, demo_text=None)
    rc = dispatch_plugin(args, ["--demo"], console=console)
    assert rc == 1
    assert "boom" in buf.getvalue()


def test_dispatch_disabled_plugin_rejected(tmp_path, monkeypatch):
    write_plugin(tmp_path / "tools", plugin_source())
    use_paths(monkeypatch, tmp_path / "tools", extra={"disabled": ["demo"]})
    console, buf = fake_console()
    args = argparse.Namespace(demo=True, demo_text=None)
    rc = dispatch_plugin(args, ["--demo"], console=console)
    assert rc == 1
    assert "disabled" in buf.getvalue()


def test_dispatch_multiple_triggered_first_nonzero_wins(tmp_path, monkeypatch):
    write_plugin(tmp_path / "tools", plugin_source(), "alpha.py")
    write_plugin(tmp_path / "tools",
                 plugin_source(meta(name="beta"), body="    return 5"), "beta.py")
    use_paths(monkeypatch, tmp_path / "tools")
    args = argparse.Namespace(alpha=True, alpha_text=None,
                              beta=True, beta_text=None)
    assert dispatch_plugin(args, ["--alpha", "--beta"]) == 5


# --------------------------------------------------------------------------- #
# run_plugin contract
# --------------------------------------------------------------------------- #

def test_run_plugin_missing_run_function(tmp_path, monkeypatch):
    path = write_plugin(tmp_path, f"PLUGIN = {meta()!r}\n", "norun.py")
    definition = pl.PluginDef("demo", "1", "", [], path, "store")
    with pytest.raises(PluginError, match="run\\(args, ctx\\)"):
        run_plugin(definition, argparse.Namespace(), make_context())


def test_run_plugin_meta_name_mismatch(tmp_path):
    path = write_plugin(tmp_path, plugin_source(meta(name="sneaky")))
    definition = pl.PluginDef("demo", "1", "", [], path, "store")
    with pytest.raises(PluginError, match="mismatch"):
        run_plugin(definition, argparse.Namespace(), make_context())


def test_run_plugin_non_int_return_rejected(tmp_path):
    path = write_plugin(tmp_path, plugin_source(body="    return 'nope'"))
    definition = pl.PluginDef("demo", "1", "", [], path, "store")
    with pytest.raises(PluginError, match="int exit code"):
        run_plugin(definition, argparse.Namespace(), make_context())


def test_run_plugin_bool_return_rejected(tmp_path):
    path = write_plugin(tmp_path, plugin_source(body="    return True"))
    definition = pl.PluginDef("demo", "1", "", [], path, "store")
    with pytest.raises(PluginError, match="int exit code"):
        run_plugin(definition, argparse.Namespace(), make_context())


def test_run_plugin_none_return_is_zero(tmp_path):
    path = write_plugin(tmp_path, plugin_source(body="    return None"))
    definition = pl.PluginDef("demo", "1", "", [], path, "store")
    assert run_plugin(definition, argparse.Namespace(), make_context()) == 0


# --------------------------------------------------------------------------- #
# PluginContext
# --------------------------------------------------------------------------- #

def test_context_guard_write_inside_env(tmp_path):
    env = create_env(tmp_path / "ws", name="demo")
    ctx = make_context(workspace=env)
    out = ctx.guard_write("sub/out.txt")
    assert out == env.root / "sub" / "out.txt"


def test_context_guard_write_escape_rejected(tmp_path):
    env = create_env(tmp_path / "ws", name="demo")
    ctx = make_context(workspace=env)
    with pytest.raises(PluginError, match="escapes"):
        ctx.guard_write("../evil.txt")


def test_context_guard_write_without_env_is_plain(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ctx = make_context(workspace=None)
    assert ctx.guard_write("out.txt") == Path("out.txt")


def test_context_results_dir(tmp_path):
    env = create_env(tmp_path / "ws", name="demo")
    assert make_context(workspace=env).results_dir == env.results_dir


def test_context_get_setting(tmp_path):
    override_setting("demo_key", "demo_value")
    assert make_context().get_setting("demo_key") == "demo_value"


# --------------------------------------------------------------------------- #
# CLI: atdork plugins list|info|run
# --------------------------------------------------------------------------- #

def test_plugins_cli_list(tmp_path, monkeypatch, capsys):
    from atdork import plugins_cli
    write_plugin(tmp_path / "tools", plugin_source())
    use_paths(monkeypatch, tmp_path / "tools")
    assert plugins_cli(["list"]) == 0
    out = capsys.readouterr().out
    assert "demo" in out and "ready" in out


def test_plugins_cli_list_empty_hint(tmp_path, monkeypatch, capsys):
    from atdork import plugins_cli
    assert plugins_cli(["list"]) == 0
    assert "install" in capsys.readouterr().out


def test_plugins_cli_info(tmp_path, monkeypatch, capsys):
    from atdork import plugins_cli
    write_plugin(tmp_path / "tools", plugin_source())
    use_paths(monkeypatch, tmp_path / "tools")
    assert plugins_cli(["info", "demo"]) == 0
    out = capsys.readouterr().out
    assert "demo" in out and "@plugins/demo" in out


def test_plugins_cli_info_unknown(tmp_path, monkeypatch):
    from atdork import plugins_cli
    write_plugin(tmp_path / "tools", plugin_source())
    use_paths(monkeypatch, tmp_path / "tools")
    assert plugins_cli(["info", "ghost"]) == 1


def test_plugins_cli_run_with_opts(tmp_path, monkeypatch):
    from atdork import plugins_cli
    marker = tmp_path / "marker.txt"
    body = f"    from pathlib import Path\n" \
           f"    Path({str(marker)!r}).write_text(str(args.demo_limit))\n" \
           f"    return 0"
    m = meta(options=[{"name": "limit", "type": "int", "default": 1}])
    write_plugin(tmp_path / "tools", plugin_source(m, body))
    use_paths(monkeypatch, tmp_path / "tools")
    rc = plugins_cli(["run", "demo", "--opt", "limit=7"])
    assert rc == 0
    assert marker.read_text() == "7"


def test_plugins_cli_run_bad_int(tmp_path, monkeypatch):
    from atdork import plugins_cli
    m = meta(options=[{"name": "limit", "type": "int"}])
    write_plugin(tmp_path / "tools", plugin_source(m))
    use_paths(monkeypatch, tmp_path / "tools")
    assert plugins_cli(["run", "demo", "--opt", "limit=NaN"]) == 1


def test_plugins_cli_run_unknown_opt(tmp_path, monkeypatch):
    from atdork import plugins_cli
    write_plugin(tmp_path / "tools", plugin_source())
    use_paths(monkeypatch, tmp_path / "tools")
    assert plugins_cli(["run", "demo", "--opt", "nope=1"]) == 1


def test_plugins_cli_run_opt_without_equals(tmp_path, monkeypatch):
    from atdork import plugins_cli
    write_plugin(tmp_path / "tools", plugin_source())
    use_paths(monkeypatch, tmp_path / "tools")
    assert plugins_cli(["run", "demo", "--opt", "plain"]) == 1


def test_plugins_cli_run_unknown_plugin(tmp_path, monkeypatch):
    from atdork import plugins_cli
    write_plugin(tmp_path / "tools", plugin_source())
    use_paths(monkeypatch, tmp_path / "tools")
    assert plugins_cli(["run", "ghost"]) == 1


def test_plugins_cli_no_args_help(capsys):
    from atdork import plugins_cli
    assert plugins_cli([]) == 1
    assert "usage" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# Package manager integration (@plugins layout in Atdork-DB)
# --------------------------------------------------------------------------- #

@pytest.fixture()
def dbrepo(tmp_path, monkeypatch):
    """Mini Atdork-DB checkout containing a nested plugin tool + dorks."""
    root = tmp_path / "Atdork-DB"
    (root / "@cve").mkdir(parents=True)
    (root / "@cve" / "cve_1.txt").write_text("dork-one\n", encoding="utf-8")
    tool = root / "@plugins" / "dorkbuilder"
    tool.mkdir(parents=True)
    (tool / "dorkbuilder.py").write_text(
        plugin_source(meta(name="dorkbuilder")), encoding="utf-8"
    )
    (tool / "_helper.py").write_text("X = 1\n", encoding="utf-8")
    build_index(repo=str(root))
    monkeypatch.setenv("ATDORK_DB_REPO", str(root))
    monkeypatch.setenv("ATDORK_PACKAGE_DIR", str(tmp_path / "store"))
    return root


def test_build_index_includes_nested_plugins(dbrepo):
    index = load_index(repo=str(dbrepo))
    names = {e.name for e in index if e.folder == "plugins"}
    assert "dorkbuilder/dorkbuilder.py" in names
    entry = next(e for e in index if e.name == "dorkbuilder/dorkbuilder.py")
    assert entry.dork_lines == 0   # code, not dork content


def test_install_plugin_tool_folder(dbrepo, tmp_path):
    # A tool folder installs every indexed file inside it (plugin + helpers).
    outcomes = install("@plugins/dorkbuilder")
    assert {o.entry.name for o in outcomes} == {
        "dorkbuilder/dorkbuilder.py", "dorkbuilder/_helper.py"}
    assert all(o.status == "installed" for o in outcomes)
    installed = tmp_path / "store" / "plugins" / "dorkbuilder" / "dorkbuilder.py"
    assert installed.is_file()


def test_install_plugin_full_file_ref(dbrepo):
    outcomes = install("@plugins/dorkbuilder/dorkbuilder.py")
    assert outcomes[0].status == "installed"


def test_install_whole_plugins_folder(dbrepo, tmp_path):
    install("@plugins")
    assert (tmp_path / "store" / "plugins" / "dorkbuilder"
            / "dorkbuilder.py").is_file()


def test_uninstall_plugin_tool_folder(dbrepo, tmp_path):
    install("@plugins/dorkbuilder")
    removed = uninstall("@plugins/dorkbuilder")
    assert removed
    assert not (tmp_path / "store" / "plugins" / "dorkbuilder"
                / "dorkbuilder.py").exists()


def test_list_installed_shows_nested_plugin(dbrepo):
    install("@plugins/dorkbuilder")
    installed = {(p.folder, p.name) for p in list_installed()}
    assert ("plugins", "dorkbuilder/dorkbuilder.py") in installed


def test_resolve_batch_file_rejects_plugin(dbrepo):
    with pytest.raises(PackageError, match="plugin"):
        resolve_batch_file("@plugins/dorkbuilder/dorkbuilder.py")


def test_resolve_batch_file_rejects_hint_names_tool(dbrepo):
    with pytest.raises(PackageError, match="@plugins/dorkbuilder\\b"):
        resolve_batch_file("@plugins/dorkbuilder/dorkbuilder.py")


def test_database_dork_rejects_plugin_module(dbrepo):
    index = load_index(repo=str(dbrepo))
    with pytest.raises(FileNotFoundError, match="plugin"):
        _resolve_dork_file("@plugins/dorkbuilder/dorkbuilder.py", index)


def test_discover_finds_installed_store_plugin(dbrepo):
    install("@plugins/dorkbuilder")
    defs = discover_plugins()
    assert [d.name for d in defs] == ["dorkbuilder"]
    assert defs[0].source == "store"


# --------------------------------------------------------------------------- #
# Config validation (fail-fast, plugins: section)
# --------------------------------------------------------------------------- #

def _layer(plugins):
    return {"version": 2, "plugins": plugins}


def test_config_plugins_valid():
    _validate_layer(_layer({
        "enabled": "auto",
        "disabled": ["x"],
        "paths": ["~/.plugins"],
        "options": {"demo": {"text": "v"}},
    }), "test")


def test_config_plugins_unknown_key():
    with pytest.raises(ConfigError, match="unknown plugins key"):
        _validate_layer(_layer({"enable": True}), "test")


def test_config_plugins_bad_enabled():
    with pytest.raises(ConfigError, match="plugins.enabled"):
        _validate_layer(_layer({"enabled": 42}), "test")


def test_config_plugins_bad_disabled():
    with pytest.raises(ConfigError, match="plugins.disabled"):
        _validate_layer(_layer({"disabled": "demo"}), "test")


def test_config_plugins_bad_paths():
    with pytest.raises(ConfigError, match="plugins.paths"):
        _validate_layer(_layer({"paths": {"a": 1}}), "test")


def test_config_plugins_bad_options():
    with pytest.raises(ConfigError, match="plugins.options.demo"):
        _validate_layer(_layer({"options": {"demo": "v"}}), "test")


def test_config_plugins_not_a_mapping():
    with pytest.raises(ConfigError, match="plugins"):
        _validate_layer({"version": 2, "plugins": ["demo"]}, "test")
