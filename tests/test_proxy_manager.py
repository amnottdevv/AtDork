"""
Unit tests for core.proxy_manager module.
"""

import time
import pytest
from unittest.mock import patch
from core.proxy_manager import (
    ProxyManager,
    is_valid_proxy,
    load_proxies_from_string,
    load_proxies_from_file,
    create_proxy_manager,
)


# ── Tests for is_valid_proxy ─────────────────────────────────────────────

@pytest.mark.parametrize("proxy,expected", [
    ("http://proxy:8080", True),
    ("https://secure:443", True),
    ("socks5://127.0.0.1:9050", True),
    ("socks5h://tor:9050", True),
    ("socks4://proxy:1080", True),
    ("proxy:8080", False),                 # no scheme
    ("http://proxy", False),               # no port
    ("http://proxy:99999", False),         # port out of range
    ("", False),
    ("not a proxy", False),
])
def test_is_valid_proxy(proxy, expected):
    assert is_valid_proxy(proxy) == expected


# ── Tests for load_proxies_from_string ──────────────────────────────────

def test_load_from_string():
    proxies = load_proxies_from_string("http://p1:8080, socks5://p2:1080")
    assert len(proxies) == 2
    assert "http://p1:8080" in proxies
    assert "socks5://p2:1080" in proxies


def test_load_from_string_single():
    proxies = load_proxies_from_string("http://p1:8080")
    assert proxies == ["http://p1:8080"]


def test_load_from_string_empty():
    proxies = load_proxies_from_string("")
    assert proxies == []


# ── Tests for load_proxies_from_file ────────────────────────────────────

def test_load_from_file(tmp_path):
    file = tmp_path / "proxies.txt"
    file.write_text("http://p1:8080\n# comment\nsocks5://p2:1080\n\n")
    proxies = load_proxies_from_file(str(file))
    assert len(proxies) == 2
    assert "http://p1:8080" in proxies
    assert "socks5://p2:1080" in proxies


# ── ProxyManager basic rotation ─────────────────────────────────────────

def test_rotation_cycles():
    pm = ProxyManager(
        proxies=["http://p1:8080", "http://p2:8080"],
        cooldown_seconds=60,
        max_failures=0,
    )
    seen = set()
    for _ in range(10):
        seen.add(pm.get_proxy())
    assert seen == {"http://p1:8080", "http://p2:8080"}


def test_strict_mode_empty_pool():
    """Constructor should raise ValueError when strict=True and no proxies."""
    with pytest.raises(ValueError, match="strict=True"):
        ProxyManager(proxies=[], strict=True)


def test_strict_mode_all_banned():
    pm = ProxyManager(
        proxies=["http://p:8080"],
        strict=True,
        cooldown_seconds=60,
        max_failures=0,
    )
    pm.report_failure("http://p:8080")   # ban
    with pytest.raises(RuntimeError):
        pm.get_proxy()


def test_cooldown_expires():
    pm = ProxyManager(
        proxies=["http://p:8080"],
        cooldown_seconds=0.5,
        max_failures=0,
    )
    proxy = pm.get_proxy()
    pm.report_failure(proxy)
    # immediately after ban
    assert pm.get_proxy() is None  # fallback
    time.sleep(0.6)
    assert pm.get_proxy() == "http://p:8080"


def test_auto_removal_after_max_failures():
    pm = ProxyManager(
        proxies=["http://p:8080"],
        cooldown_seconds=1,
        max_failures=2,
    )
    p = pm.get_proxy()
    pm.report_failure(p)      # 1
    assert len(pm.proxies) == 1
    pm.report_failure(p)      # 2 -> remove
    assert len(pm.proxies) == 0
    assert pm.get_proxy() is None


def test_no_removal_when_max_failures_zero():
    pm = ProxyManager(
        proxies=["http://p:8080"],
        cooldown_seconds=1,
        max_failures=0,     # never remove
    )
    p = pm.get_proxy()
    for _ in range(5):
        pm.report_failure(p)
    assert len(pm.proxies) == 1


# ── Proxy statistics ────────────────────────────────────────────────────

def test_stats():
    pm = ProxyManager(proxies=["http://p:8080"])
    p = pm.get_proxy()
    pm.report_success(p)
    pm.report_failure(p)
    stats = pm.get_stats_summary()
    assert stats["total_success"] == 1
    assert stats["total_failure"] == 1


def test_stats_consecutive_reset_on_success():
    pm = ProxyManager(proxies=["http://p:8080"], max_failures=3)
    p = pm.get_proxy()
    pm.report_failure(p)
    pm.report_success(p)  # reset consecutive
    pm.report_failure(p)
    # should still be in pool because consecutive failure count was reset
    assert len(pm.proxies) == 1


# ── Dynamic add/remove ──────────────────────────────────────────────────

def test_add_proxy():
    pm = ProxyManager(proxies=["http://p1:8080"])
    pm.add_proxy("http://p2:8080")
    assert len(pm.proxies) == 2


def test_add_invalid_proxy_ignored():
    pm = ProxyManager(proxies=["http://p1:8080"])
    pm.add_proxy("bad_proxy")
    assert len(pm.proxies) == 1


def test_remove_proxy():
    pm = ProxyManager(proxies=["http://p1:8080"])
    pm.remove_proxy("http://p1:8080")
    assert len(pm.proxies) == 0


# ── Factory function create_proxy_manager ───────────────────────────────

def test_create_from_args_only():
    pm = create_proxy_manager(
        proxy_arg="http://a:8080,socks5://b:1080",
        proxy_file=None,
        enable_tor=False,
        cooldown=30,
        strict=False,
        max_failures=5,
    )
    assert pm is not None
    assert len(pm.proxies) >= 2  # 2 from args


def test_create_with_file(tmp_path):
    file = tmp_path / "proxies.txt"
    file.write_text("http://file1:8080\nhttp://file2:8080")
    pm = create_proxy_manager(
        proxy_arg="http://arg:8080",
        proxy_file=str(file),
        enable_tor=False,
    )
    # Should contain 3 unique proxies (arg + 2 file)
    assert len(pm.proxies) == 3


def test_create_with_tor_available():
    with patch("core.proxy_manager._check_tor_socks_port", return_value=True):
        pm = create_proxy_manager(
            proxy_arg=None,
            proxy_file=None,
            enable_tor=True,
        )
        assert "socks5h://127.0.0.1:9050" in pm.proxies


def test_create_with_tor_unavailable():
    with patch("core.proxy_manager._check_tor_socks_port", return_value=False):
        pm = create_proxy_manager(
            proxy_arg=None,
            proxy_file=None,
            enable_tor=True,
        )
        assert "socks5h://127.0.0.1:9050" not in pm.proxies


def test_create_strict_mode():
    pm = create_proxy_manager(
        proxy_arg="http://p:8080",
        strict=True,
    )
    # remove proxy to trigger strict behavior
    pm.remove_proxy("http://p:8080")
    with pytest.raises(RuntimeError):
        pm.get_proxy()