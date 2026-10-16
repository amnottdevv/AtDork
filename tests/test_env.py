"""
Unit tests for the environment (workspace) layer: core/env.py, the env
config layer in core/config.py, and atdork.apply_env_to_args.

All filesystem effects are confined to tmp_path (HOME is patched so the
env registry never touches the real ~/.config).
"""

import argparse
import os

import pytest

from core.env import (
    Env,
    EnvEscapeError,
    EnvError,
    MARKER_NAME,
    create_env,
    destroy_env,
    guard_if_env,
    read_registry,
    resolve_env,
    set_active_env,
    unregister_env,
)
from core.config import _CURRENT, get_setting, load_config, override_setting


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Registry + ATDORK_ENV + config state never leak between tests."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("ATDORK_ENV", raising=False)
    _CURRENT.clear()
    yield
    _CURRENT.clear()


def make_args(**overrides):
    base = dict(
        output_dir=None, output=None, log_file="atdork.log", db_path="atdork.db",
        cache_db="atdork_cache.db", package_dir=None, db_repo=None,
        database_path=None, export_db=None, ghdb_file=None,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


# ── Creation ───────────────────────────────────────────────────────────────

def test_create_layout_and_marker(tmp_path):
    env = create_env(tmp_path / "ws", name="demo")
    root = env.root
    assert (root / MARKER_NAME).is_file()
    for rel in (".config", ".config/packages", "cache", "results", "logs",
                "state", "tmp"):
        assert (root / rel).is_dir()
    assert env.name == "demo"
    # registered automatically
    assert str(root) in read_registry()["known"]


def test_create_is_idempotent(tmp_path):
    env1 = create_env(tmp_path / "ws", name="first")
    env2 = create_env(tmp_path / "ws")          # init alias — no error
    assert env2.name == "first"                 # marker preserved
    create_env(tmp_path / "ws", name="new", force=True)
    assert Env.at(tmp_path / "ws").name == "new"


def test_env_at_returns_none_without_marker(tmp_path):
    assert Env.at(tmp_path / "nope") is None


# ── Resolution precedence ─────────────────────────────────────────────────

def test_resolution_precedence(tmp_path, monkeypatch):
    a = create_env(tmp_path / "a")
    b = create_env(tmp_path / "b")
    c = create_env(tmp_path / "c")
    set_active_env(c.root)                       # registry (lowest)
    monkeypatch.setenv("ATDORK_ENV", str(b.root))  # env var
    assert resolve_env(str(a.root)).root == a.root  # CLI flag wins
    assert resolve_env().root == b.root              # then env var
    monkeypatch.delenv("ATDORK_ENV")
    assert resolve_env().root == c.root              # then registry


def test_resolution_none_when_unset(tmp_path):
    assert resolve_env() is None


def test_explicit_invalid_env_raises(tmp_path, monkeypatch):
    with pytest.raises(EnvError, match="not an AtDork environment"):
        resolve_env(str(tmp_path / "ghost"))
    monkeypatch.setenv("ATDORK_ENV", str(tmp_path / "ghost"))
    with pytest.raises(EnvError, match="ATDORK_ENV"):
        resolve_env()


def test_stale_registry_entry_is_ignored(tmp_path):
    set_active_env(tmp_path / "deleted")   # never created
    assert resolve_env() is None


def test_unregister_clears_active(tmp_path):
    env = create_env(tmp_path / "ws")
    set_active_env(env.root)
    unregister_env(env.root)
    assert read_registry()["active"] is None
    assert str(env.root) not in read_registry()["known"]


# ── Strict path guard ──────────────────────────────────────────────────────

def test_guard_inside_root(tmp_path):
    env = create_env(tmp_path / "ws")
    assert env.guard_write(str(env.root / "results" / "x.json")) == \
        (env.root / "results" / "x.json").resolve()


def test_guard_relative_resolves_against_root(tmp_path, monkeypatch):
    env = create_env(tmp_path / "ws")
    monkeypatch.chdir(tmp_path)            # CWD deliberately outside
    assert env.guard_write("results/x.json") == \
        (env.root / "results" / "x.json").resolve()


def test_guard_rejects_absolute_outside(tmp_path):
    env = create_env(tmp_path / "ws")
    with pytest.raises(EnvEscapeError, match="outside the environment"):
        env.guard_write(tmp_path / "outside.txt")


def test_guard_rejects_dotdot_escape(tmp_path):
    env = create_env(tmp_path / "ws")
    with pytest.raises(EnvEscapeError):
        env.guard_write("../outside.txt")
    with pytest.raises(EnvEscapeError):
        env.guard_write(str(env.root / "results" / ".." / ".." / "leak.txt"))


def test_guard_rejects_symlink_escape(tmp_path):
    env = create_env(tmp_path / "ws")
    (env.root / "tmp" / "evil").symlink_to(tmp_path)   # symlink → outside
    with pytest.raises(EnvEscapeError):
        env.guard_write("tmp/evil/leak.db")


def test_guard_if_env_passthrough_without_env(tmp_path):
    assert guard_if_env("/anywhere/x.txt") == "/anywhere/x.txt"
    assert guard_if_env(None) is None
    env = create_env(tmp_path / "ws")
    set_active_env(env.root)
    with pytest.raises(EnvEscapeError):
        guard_if_env(str(tmp_path / "outside.txt"))


# ── apply_env_to_args (atdork.py wiring) ──────────────────────────────────

def test_apply_defaults_redirect_into_env(tmp_path):
    from atdork import apply_env_to_args
    env = create_env(tmp_path / "ws")
    args = make_args()
    apply_env_to_args(args, env, argv=["-q", "x"])     # no path flags on CLI
    assert args.output_dir == str(env.results_dir)
    assert args.log_file == str(env.log_file)
    assert args.db_path == str(env.db_path)
    assert args.cache_db == str(env.cache_db)
    assert args.package_dir == str(env.packages_dir)
    assert args.db_repo == str(env.db_repo)


def test_apply_cli_inside_root_kept(tmp_path):
    from atdork import apply_env_to_args
    env = create_env(tmp_path / "ws")
    args = make_args(output_dir=str(env.root / "myresults"))
    apply_env_to_args(args, env, argv=["--output-dir", str(env.root / "myresults")])
    assert args.output_dir == str((env.root / "myresults").resolve())


def test_apply_cli_outside_root_rejected(tmp_path):
    from atdork import apply_env_to_args
    env = create_env(tmp_path / "ws")
    args = make_args(output_dir=str(tmp_path / "loot"))
    with pytest.raises(EnvEscapeError):
        apply_env_to_args(args, env, argv=["--output-dir", str(tmp_path / "loot")])
    args = make_args(output=str(tmp_path / "loot.txt"))
    with pytest.raises(EnvEscapeError):
        apply_env_to_args(args, env, argv=["-o", str(tmp_path / "loot.txt")])


def test_apply_relative_cli_flag_resolves_to_root(tmp_path, monkeypatch):
    from atdork import apply_env_to_args
    env = create_env(tmp_path / "ws")
    monkeypatch.chdir(tmp_path)
    args = make_args(output="results/inline.json")
    apply_env_to_args(args, env, argv=["-o", "results/inline.json"])
    assert args.output == str(env.results_dir / "inline.json")


def test_apply_config_sourced_output_redirects(tmp_path):
    """-o value coming from config (not CLI) is env-owned → results dir."""
    from atdork import apply_env_to_args
    env = create_env(tmp_path / "ws")
    args = make_args(output="dump.txt", export_db="export.json")
    apply_env_to_args(args, env, argv=["-q", "x"])     # flags not on argv
    assert args.output == str(env.results_dir / "dump.txt")
    assert args.export_db == str(env.state_dir / "export.json")


# ── Config integration ────────────────────────────────────────────────────

def test_env_config_layer_and_cwd_skip(tmp_path, monkeypatch):
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    (cwd / "atdork.yaml").write_text("max_results: 11\nregion: uk-en\n")
    env = create_env(tmp_path / "ws")
    env.config_file.write_text("version: 2\nsearch:\n  max_results: 77\n")
    monkeypatch.chdir(cwd)

    # env active (env_config_path set) → CWD file skipped, env layer wins
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("ATDORK_MAX_RESULTS", raising=False)
        config = load_config(None, env_config_path=str(env.config_file))
    assert config["max_results"] == 77
    assert config["region"] == "us-en"       # cwd file not merged

    # without env layer → cwd discovery as before
    config = load_config(None, env_config_path=None)
    assert config["max_results"] == 11


def test_env_config_below_explicit_config(tmp_path, monkeypatch):
    env = create_env(tmp_path / "ws")
    env.config_file.write_text("version: 2\nsearch:\n  max_results: 77\n")
    explicit = tmp_path / "explicit.yml"
    explicit.write_text("max_results: 5\n")
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("ATDORK_MAX_RESULTS", raising=False)
        config = load_config(str(explicit), env_config_path=str(env.config_file))
    assert config["max_results"] == 5        # --config still wins


def test_override_setting_visible_to_get_setting(tmp_path):
    env = create_env(tmp_path / "ws")
    load_config(filepath="/nonexistent/x.yml")
    override_setting("package_dir", str(env.packages_dir))
    override_setting("db_repo", str(env.db_repo))
    assert get_setting("package_dir") == str(env.packages_dir)
    assert get_setting("db_repo") == str(env.db_repo)


# ── Destroy ────────────────────────────────────────────────────────────────

def test_destroy_keeps_files_by_default(tmp_path):
    env = create_env(tmp_path / "ws")
    (env.results_dir / "keep.txt").write_text("data")
    destroy_env(env.root, delete_files=False)
    assert (env.root / "results" / "keep.txt").is_file()
    assert not (env.root / MARKER_NAME).exists()
    assert str(env.root) not in read_registry()["known"]


def test_destroy_delete_removes_folder(tmp_path):
    env = create_env(tmp_path / "ws")
    destroy_env(env.root, delete_files=True)
    assert not env.root.exists()


def test_destroy_non_env_raises(tmp_path):
    with pytest.raises(EnvError, match="not an AtDork environment"):
        destroy_env(tmp_path / "plain")


# ── env subcommand dispatch ────────────────────────────────────────────────

def test_env_cli_create_list_which(tmp_path, capsys):
    from atdork import env_cli
    assert env_cli(["create", str(tmp_path / "ws"), "--name", "cli"]) == 0
    out = capsys.readouterr().out
    assert "Environment ready" in out and "cli" in out or "ws" in out

    assert env_cli(["list"]) == 0
    assert str(tmp_path / "ws") in capsys.readouterr().out

    assert env_cli(["use", str(tmp_path / "ws")]) == 0
    assert env_cli(["which"]) == 0
    out = capsys.readouterr().out
    assert str(tmp_path / "ws") in out and "results" in out


def test_env_cli_which_without_env(tmp_path, capsys):
    from atdork import env_cli
    assert env_cli(["which"]) == 0
    assert "No environment active" in capsys.readouterr().out


def test_env_cli_use_invalid_returns_error(tmp_path, capsys):
    from atdork import env_cli
    assert env_cli(["use", str(tmp_path / "ghost")]) == 1
    out = capsys.readouterr().out
    # Rich wraps lines, so assert on wrap-safe fragments
    assert "Environment error" in out
    assert "atdork env create" in out


def test_env_cli_destroy_unregister(tmp_path, capsys):
    from atdork import env_cli
    env_cli(["create", str(tmp_path / "ws")])
    capsys.readouterr()
    assert env_cli(["destroy", str(tmp_path / "ws")]) == 0
    assert (tmp_path / "ws").is_dir()        # files kept without --delete
    assert not (tmp_path / "ws" / MARKER_NAME).exists()
