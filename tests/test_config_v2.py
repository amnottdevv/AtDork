"""
Unit tests for the schema-v2 configuration loader (core/config.py).

Covers: nested sections, ${ENV} interpolation, strict v2 validation,
layered discovery (global → CWD → explicit), and v1 back-compat.
"""

import os

import pytest
from unittest.mock import patch

from core.config import (
    ConfigError,
    get_setting,
    load_config,
)


ENV_CLEAN = {"PATH": os.environ.get("PATH", "")}


# ── Nested sections ────────────────────────────────────────────────────────

def test_v2_sections_loaded_and_applied(tmp_path):
    file = tmp_path / "atdork.yml"
    file.write_text("""
version: 2
search:
  max_results: 33
  backend: serper
  fallback: [google, serper, brave]
engines:
  serper:
    type: api
    api_key: literal-key-123
    qps: 2
profiles:
  resilient: [google, serper]
resilience:
  circuit_breaker:
    failure_threshold: 5
  cooldown: 60
output:
  format: json
  dir: /tmp/out
""")
    with patch.dict(os.environ, ENV_CLEAN, clear=True):
        config = load_config(filepath=str(file))

    # search section overrides flat defaults
    assert config["max_results"] == 33
    assert config["backend"] == "serper"
    # sections stored under their names
    assert config["search"]["fallback"] == ["google", "serper", "brave"]
    assert config["engines"]["serper"]["qps"] == 2
    assert config["profiles"]["resilient"] == ["google", "serper"]
    assert config["resilience"]["circuit_breaker"]["failure_threshold"] == 5
    assert config["resilience"]["cooldown"] == 60
    # output section flattens onto CLI-facing keys
    assert config["format"] == "json"
    assert config["output_dir"] == "/tmp/out"


def test_get_setting_reads_sections(tmp_path):
    file = tmp_path / "atdork.yml"
    file.write_text("""
version: 2
engines:
  serper:
    type: api
    api_key: k
""")
    with patch.dict(os.environ, ENV_CLEAN, clear=True):
        load_config(filepath=str(file))
        assert get_setting("engines")["serper"]["api_key"] == "k"
        # env strings must never clobber dict sections
        with patch.dict(os.environ, {"ATDORK_ENGINES": "garbage"}):
            assert get_setting("engines") == {"serper": {"type": "api", "api_key": "k"}}
    # no section → default
    from core.config import _CURRENT
    _CURRENT.clear()
    assert get_setting("engines", {}) == {}


# ── Strict v2 validation ───────────────────────────────────────────────────

def test_v2_unknown_root_key_raises(tmp_path):
    file = tmp_path / "atdork.yml"
    file.write_text("version: 2\nmax_results: 5\nbogus_key: 1\n")
    with patch.dict(os.environ, ENV_CLEAN, clear=True):
        with pytest.raises(ConfigError, match="bogus_key"):
            load_config(filepath=str(file))


def test_v2_unknown_search_key_raises(tmp_path):
    file = tmp_path / "atdork.yml"
    file.write_text("version: 2\nsearch:\n  max_resultz: 5\n")
    with patch.dict(os.environ, ENV_CLEAN, clear=True):
        with pytest.raises(ConfigError, match="max_resultz"):
            load_config(filepath=str(file))


def test_v2_bad_section_type_raises(tmp_path):
    file = tmp_path / "atdork.yml"
    file.write_text('version: 2\nprofiles:\n  resilient: "google,serper"\n')
    with patch.dict(os.environ, ENV_CLEAN, clear=True):
        with pytest.raises(ConfigError, match="profiles.resilient"):
            load_config(filepath=str(file))


def test_v2_unsupported_version_raises(tmp_path):
    file = tmp_path / "atdork.yml"
    file.write_text("version: 99\n")
    with patch.dict(os.environ, ENV_CLEAN, clear=True):
        with pytest.raises(ConfigError, match="unsupported config version"):
            load_config(filepath=str(file))


def test_v2_unknown_engine_type_raises(tmp_path):
    file = tmp_path / "atdork.yml"
    file.write_text("engines:\n  x:\n    type: scraping\n")
    with patch.dict(os.environ, ENV_CLEAN, clear=True):
        with pytest.raises(ConfigError, match="type"):
            load_config(filepath=str(file))


def test_broken_yaml_raises_config_error(tmp_path):
    file = tmp_path / "atdork.yml"
    file.write_text("key: [unclosed\n  bad indent: :\n")
    with patch.dict(os.environ, ENV_CLEAN, clear=True):
        with pytest.raises(ConfigError, match="failed to parse YAML"):
            load_config(filepath=str(file))


def test_v1_explicit_version_stays_lenient(tmp_path):
    file = tmp_path / "atdork.yml"
    file.write_text("version: 1\nmax_results: 8\nrandom_junk: true\n")
    with patch.dict(os.environ, ENV_CLEAN, clear=True):
        config = load_config(filepath=str(file))
    assert config["max_results"] == 8
    assert "random_junk" not in config


# ── ${ENV} interpolation ───────────────────────────────────────────────────

def test_env_interpolation(tmp_path):
    file = tmp_path / "atdork.yml"
    file.write_text("version: 2\nuser_agent: ${MY_TEST_UA}\n")
    with patch.dict(os.environ, {**ENV_CLEAN, "MY_TEST_UA": "Agent/9.9"}):
        config = load_config(filepath=str(file))
    assert config["user_agent"] == "Agent/9.9"


def test_env_interpolation_default_syntax(tmp_path):
    file = tmp_path / "atdork.yml"
    file.write_text("version: 2\nuser_agent: ${UNSET_VAR_XYZ:-FallbackUA}\n")
    with patch.dict(os.environ, ENV_CLEAN, clear=True):
        config = load_config(filepath=str(file))
    assert config["user_agent"] == "FallbackUA"


def test_missing_env_in_engine_api_key_raises(tmp_path):
    file = tmp_path / "atdork.yml"
    file.write_text("""
version: 2
engines:
  serper:
    type: api
    api_key: ${SERPER_API_KEY}
""")
    with patch.dict(os.environ, ENV_CLEAN, clear=True):
        with pytest.raises(ConfigError, match=r"engines\.serper\.api_key: environment 'SERPER_API_KEY' is not set"):
            load_config(filepath=str(file))


def test_missing_env_elsewhere_only_warns(tmp_path, caplog):
    file = tmp_path / "atdork.yml"
    file.write_text("version: 2\nproxy: socks5://${SOME_PROXY_VAR}\n")
    with patch.dict(os.environ, ENV_CLEAN, clear=True):
        config = load_config(filepath=str(file))
    # does not raise; value degraded to empty
    assert config["proxy"] == "socks5://"


# ── Layered discovery ──────────────────────────────────────────────────────

def test_layering_global_cwd_explicit(tmp_path):
    """Precedence: global < working-directory < explicit (--config)."""
    global_dir = tmp_path / "home"
    (global_dir / ".config" / "atdork").mkdir(parents=True)
    (global_dir / ".config" / "atdork" / "config.yml").write_text(
        "max_results: 11\nregion: us-en\ndebug: true\n"
    )

    cwd = tmp_path / "cwd"
    cwd.mkdir()
    (cwd / "atdork.yaml").write_text("max_results: 22\nregion: uk-en\n")

    explicit = tmp_path / "explicit.yml"
    explicit.write_text("max_results: 33\n")

    env = {**ENV_CLEAN, "HOME": str(global_dir)}
    with patch.dict(os.environ, env, clear=True):
        import unittest.mock as mock
        with mock.patch("os.getcwd", return_value=str(cwd)):
            config = load_config(filepath=str(explicit))

    # each layer overrides the previous one for the keys it sets
    assert config["max_results"] == 33   # explicit wins
    assert config["region"] == "uk-en"   # cwd wins over global
    assert config["debug"] is True       # only in global


def test_global_only_discovery(tmp_path):
    global_dir = tmp_path / "home"
    (global_dir / ".config" / "atdork").mkdir(parents=True)
    (global_dir / ".config" / "atdork" / "config.yml").write_text("max_results: 44\n")
    empty_cwd = tmp_path / "empty"
    empty_cwd.mkdir()
    import unittest.mock as mock
    with patch.dict(os.environ, {**ENV_CLEAN, "HOME": str(global_dir)}, clear=True):
        with mock.patch("os.getcwd", return_value=str(empty_cwd)):
            config = load_config(filepath="/nonexistent/atdork.yaml")
    assert config["max_results"] == 44


def test_atdork_config_env_selects_path(tmp_path):
    file = tmp_path / "chosen.yml"
    file.write_text("max_results: 55\n")
    with patch.dict(os.environ, {**ENV_CLEAN, "ATDORK_CONFIG": str(file)}, clear=True):
        config = load_config()
    assert config["max_results"] == 55
