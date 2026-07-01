"""
Atdork – Error Classifier (core/case/error_classifier.py)
Memetakan exception mentah ke kategori yang bisa ditindaklanjuti.

Digunakan oleh: retry_handler, fallback_manager, batch_runner.
"""

import logging
from typing import Union

logger = logging.getLogger(__name__)


class ErrorCategory:
    """Kategori error yang digunakan oleh seluruh sistem case."""
    TRANSIENT   = "transient"      # timeout, connection reset → retry
    RATE_LIMIT  = "rate_limit"     # HTTP 429 → jeda panjang, ganti backend
    BLOCKED     = "blocked"        # HTTP 403, CAPTCHA → ganti backend/proxy
    PROXY_FAIL  = "proxy_fail"     # proxy mati / tidak merespons / cooldown
    FATAL       = "fatal"          # error parsing, bug → hentikan


def classify_error(exception: Exception) -> str:
    """
    Klasifikasikan exception menjadi salah satu ErrorCategory.

    Args:
        exception: Exception yang ditangkap.

    Returns:
        Salah satu string dari ErrorCategory.
    """
    if not isinstance(exception, Exception):
        logger.warning("classify_error dipanggil dengan non‑Exception: %s", type(exception))
        return ErrorCategory.FATAL

    try:
        msg = str(exception).lower()
    except Exception as e:
        logger.error("Gagal mengambil pesan exception: %s", e)
        msg = ""

    # ── 1. Rate limit ──────────────────────────────────────────────
    if any(kw in msg for kw in (
        "429", "too many requests", "rate limit", "rate exceeded",
        "request was throttled", "slow down",
    )):
        return ErrorCategory.RATE_LIMIT

    # ── 2. Blocked ─────────────────────────────────────────────────
    if any(kw in msg for kw in (
        "403", "forbidden", "blocked", "access denied", "captcha",
        "sorry", "unusual traffic", "access blocked",
    )):
        return ErrorCategory.BLOCKED

    # ── 3. Proxy / koneksi / cooldown ──────────────────────────────
    if any(kw in msg for kw in (
        "proxy", "socks", "connection refused", "tunnel",
        "cannot connect", "cooldown", "no proxy",
        "tidak ada proxy", "semua proxy", "strict mode",
        "proxy authentication", "407", "auth required",
    )):
        return ErrorCategory.PROXY_FAIL

    # ── 4. Transient (timeout, connection error) ───────────────────
    if any(kw in msg for kw in (
        "timeout", "timed out", "connection error",
        "connection reset", "broken pipe", "eof", "eof occurred",
        "incomplete read", "try again",
    )):
        return ErrorCategory.TRANSIENT

    # ── 5. Cek subclass dari scanner jika tersedia ─────────────────
    try:
        from atdork.core.scanner import RateLimitError, BlockedError, ProxyError
        if isinstance(exception, RateLimitError):
            return ErrorCategory.RATE_LIMIT
        if isinstance(exception, BlockedError):
            return ErrorCategory.BLOCKED
        if isinstance(exception, ProxyError):
            return ErrorCategory.PROXY_FAIL
    except ImportError:
        pass

    # ── 6. Default: fatal ──────────────────────────────────────────
    return ErrorCategory.FATAL
