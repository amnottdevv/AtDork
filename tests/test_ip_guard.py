"""
Unit tests untuk wiring --ip-guard (core.case.ip_guard + atdork._verify_ip_guard).

Regresi v1.3.9.6: IPGuard.check() tidak pernah dipanggil di alur mana pun,
dan --ip-guard tanpa --strict bahkan tidak diinisialisasi.
"""

from unittest.mock import MagicMock, patch

import pytest

from core.case.ip_guard import IPGuard, IPGuardError
import atdork


REAL_IP = "203.0.113.10"
PROXY_IP = "198.51.100.7"
PROXY_URL = "http://proxy.example:8080"


def _guard(strict=True):
    g = IPGuard(REAL_IP, strict=strict)
    return g


# ── IPGuard.check / enforce ───────────────────────────────────────────────

def test_check_detects_real_ip_leak():
    g = _guard(strict=True)
    with patch.object(IPGuard, "get_public_ip", side_effect=[PROXY_IP, REAL_IP]):
        g.establish_baseline(PROXY_URL)   # IP via proxy
        safe, warnings = g.check(PROXY_URL)  # IP yang terlihat = IP asli → bocor
    assert safe is False
    assert g.leak_detected is True
    assert any("leak" in w.lower() or "real ip" in w.lower() for w in warnings)


def test_enforce_strict_stops_on_leak():
    g = _guard(strict=True)
    with patch.object(IPGuard, "get_public_ip", side_effect=[PROXY_IP, REAL_IP]):
        g.establish_baseline(PROXY_URL)
        ok, panic, warnings = g.enforce(PROXY_URL)
    assert ok is False
    assert panic and "IP LEAK" in panic


def test_enforce_non_strict_continues_with_warnings():
    g = _guard(strict=False)
    with patch.object(IPGuard, "get_public_ip", side_effect=[PROXY_IP, REAL_IP]):
        g.establish_baseline(PROXY_URL)
        ok, panic, warnings = g.enforce(PROXY_URL)
    assert ok is True          # boleh lanjut
    assert panic is None
    assert warnings             # tetap peringatkan pengguna
    assert g.leak_detected is True


def test_enforce_safe_when_proxy_works():
    g = _guard(strict=True)
    with patch.object(IPGuard, "get_public_ip", return_value=PROXY_IP):
        g.establish_baseline(PROXY_URL)
        ok, panic, warnings = g.enforce(PROXY_URL)
    assert ok is True and panic is None and warnings == []


def test_provider_down_is_not_treated_as_leak():
    """Provider IP-check mati → jangan bunuh tool di mode strict."""
    g = _guard(strict=True)
    with patch.object(IPGuard, "get_public_ip", return_value=PROXY_IP):
        g.establish_baseline(PROXY_URL)
    with patch.object(IPGuard, "get_public_ip", return_value=None):
        ok, panic, warnings = g.enforce(PROXY_URL)
    assert ok is True          # tidak ada bukti kebocoran
    assert panic is None
    assert warnings             # tapi tetap di-warning


def test_baseline_same_as_real_ip_flags_leak():
    g = _guard(strict=True)
    with patch.object(IPGuard, "get_public_ip", return_value=REAL_IP):
        g.establish_baseline(PROXY_URL)
    assert g.leak_detected is True  # proxy tidak bekerja → IP asli terlihat


# ── Wiring di atdork ──────────────────────────────────────────────────────

def _args(**over):
    base = dict(
        resilient=False, adaptive_delay=False, ip_guard=True, strict=True, retries=2,
    )
    base.update(over)
    return MagicMock(**base)


def test_setup_case_modules_without_proxy_skips_guard():
    """Tanpa proxy, IP Guard tak bermakna → dilewati (dan tanpa panggilan jaringan)."""
    with patch.object(IPGuard, "get_public_ip") as mock_ip:
        modules = atdork._setup_case_modules(_args(), None)
    mock_ip.assert_not_called()
    assert modules["ip_guard"] is None


def test_setup_case_modules_with_proxy_creates_guard_with_baseline():
    proxy_manager = MagicMock()
    proxy_manager.get_proxy.return_value = PROXY_URL
    with patch.object(IPGuard, "get_public_ip", return_value=REAL_IP), \
         patch.object(IPGuard, "establish_baseline") as mock_baseline:
        modules = atdork._setup_case_modules(_args(ip_guard=True, strict=True), proxy_manager)
    assert isinstance(modules["ip_guard"], IPGuard)
    assert modules["ip_guard"].strict is True
    mock_baseline.assert_called_once_with(PROXY_URL)


def test_setup_case_modules_ip_guard_works_without_strict():
    """Bug lama: --ip-guard tanpa --strict sama sekali tidak diproses."""
    proxy_manager = MagicMock()
    proxy_manager.get_proxy.return_value = PROXY_URL
    with patch.object(IPGuard, "get_public_ip", return_value=REAL_IP), \
         patch.object(IPGuard, "establish_baseline"):
        modules = atdork._setup_case_modules(_args(ip_guard=True, strict=False), proxy_manager)
    assert isinstance(modules["ip_guard"], IPGuard)
    assert modules["ip_guard"].strict is False


def test_verify_ip_guard_records_stats_and_returns_panic():
    guard = MagicMock()
    guard.enforce.return_value = (False, "PANIC MESSAGE", ["leak detail"])
    stats = MagicMock()
    proxy_manager = MagicMock()
    proxy_manager.get_proxy.return_value = PROXY_URL

    ok, panic = atdork._verify_ip_guard(guard, proxy_manager, stats, phase="pre-run")

    assert ok is False
    assert panic == "PANIC MESSAGE"
    stats.record_ip_guard.assert_called_once_with(check=True, leak=True)
    guard.enforce.assert_called_once_with(PROXY_URL)


def test_verify_ip_guard_noop_when_disabled():
    stats = MagicMock()
    ok, panic = atdork._verify_ip_guard(None, None, stats, phase="pre-run")
    assert ok is True and panic == ""
    stats.record_ip_guard.assert_not_called()


def test_verify_ip_guard_survives_guard_error():
    """Error tak terduga di guard tidak boleh menjatuhkan seluruh run."""
    guard = MagicMock()
    guard.enforce.side_effect = RuntimeError("meledak")
    ok, panic = atdork._verify_ip_guard(guard, None, None)
    assert ok is True and panic == ""
