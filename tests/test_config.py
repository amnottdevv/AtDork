"""
Unit tests for core.config module.
"""

import os
import pytest
from unittest.mock import patch
from core.config import load_config, DEFAULT_CONFIG


# ── Default configuration ────────────────────────────────────────────────

def test_load_config_no_file_no_env():
    """Without any config file or env vars, defaults should be returned."""
    with patch.dict(os.environ, {}, clear=True):
        config = load_config(filepath="/nonexistent/atdork.yaml")
    # Max results default
    assert config["max_results"] == 20
    assert config["region"] == "us-en"


# ── YAML config file ────────────────────────────────────────────────────

def test_load_config_from_yaml(tmp_path):
    file = tmp_path / "atdork.yaml"
    file.write_text("""
max_results: 50
region: "uk-en"
backend: "google"
debug: true
""")
    with patch.dict(os.environ, {}, clear=True):
        config = load_config(filepath=str(file))
    assert config["max_results"] == 50
    assert config["region"] == "uk-en"
    assert config["backend"] == "google"
    assert config["debug"] is True


def test_load_config_ignores_unknown_keys(tmp_path):
    file = tmp_path / "atdork.yaml"
    file.write_text("""
max_results: 50
some_random_key: "ignored"
""")
    with patch.dict(os.environ, {}, clear=True):
        config = load_config(filepath=str(file))
    assert "some_random_key" not in config


# ── Environment variable override ────────────────────────────────────────

def test_env_override():
    env_vars = {
        "ATDORK_MAX_RESULTS": "99",
        "ATDORK_REGION": "ru-ru",
        "ATDORK_DEBUG": "true",
        "ATDORK_STRICT": "1",
    }
    with patch.dict(os.environ, env_vars, clear=True):
        config = load_config(filepath="/nonexistent/atdork.yaml")
    assert config["max_results"] == 99
    assert config["region"] == "ru-ru"
    assert config["debug"] is True
    assert config["strict"] is True


def test_env_override_over_yaml(tmp_path):
    """Environment variables should take precedence over YAML."""
    file = tmp_path / "atdork.yaml"
    file.write_text("""
max_results: 10
region: "us-en"
""")
    env_vars = {"ATDORK_MAX_RESULTS": "42"}
    with patch.dict(os.environ, env_vars, clear=True):
        config = load_config(filepath=str(file))
    assert config["max_results"] == 42       # env wins
    assert config["region"] == "us-en"       # still from yaml


def test_env_type_conversion():
    """Env vars should be converted to the correct type (int, float, bool)."""
    env_vars = {
        "ATDORK_MAX_RESULTS": "88",
        "ATDORK_TIMEOUT": "15",
        "ATDORK_DELAY": "1.5",
        "ATDORK_DEBUG": "0",          # false
        "ATDORK_STRICT": "yes",       # true
    }
    with patch.dict(os.environ, env_vars, clear=True):
        config = load_config(filepath="/nonexistent/atdork.yaml")
    assert config["max_results"] == 88
    assert config["timeout"] == 15
    assert config["delay"] == 1.5
    assert config["debug"] is False
    assert config["strict"] is True


# ── Custom config path ──────────────────────────────────────────────────

def test_custom_config_path(tmp_path):
    file = tmp_path / "custom.yaml"
    file.write_text("max_results: 33")
    with patch.dict(os.environ, {}, clear=True):
        config = load_config(filepath=str(file))
    assert config["max_results"] == 33