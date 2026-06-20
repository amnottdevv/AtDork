"""
Atdork – Circuit Breaker (core/case/circuit_breaker.py)
Mencegah percobaan berulang ke resource yang sudah jelas gagal (backend/proxy).

Dilengkapi try‑except di semua method publik agar error terlihat jelas.
"""

import time
import threading
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class CircuitBreakerError(Exception):
    """Exception khusus untuk CircuitBreaker."""
    pass


class CircuitBreaker:
    """
    Circuit breaker dengan tiga status:
      - CLOSED   → resource sehat, permintaan diizinkan
      - OPEN     → resource gagal, permintaan ditolak selama cooldown
      - HALF_OPEN → cooldown berakhir, satu permintaan diizinkan untuk menguji

    Attributes:
        threshold (int): jumlah kegagalan berturut-turut sebelum membuka sirkuit
        cooldown (float): durasi (detik) sirkuit tetap terbuka sebelum setengah terbuka
    """

    def __init__(self, threshold: int = 3, cooldown: float = 120.0):
        if threshold < 1:
            raise CircuitBreakerError("threshold harus >= 1")
        if cooldown <= 0:
            raise CircuitBreakerError("cooldown harus > 0")

        self.threshold = threshold
        self.cooldown = cooldown
        self._failures: dict[str, int] = defaultdict(int)
        self._open_until: dict[str, float] = {}
        self._lock = threading.Lock()

    @property
    def open_circuits(self) -> list[str]:
        """Daftar resource yang sedang dalam status OPEN."""
        now = time.time()
        with self._lock:
            try:
                return [k for k, v in self._open_until.items() if now < v]
            except Exception as e:
                logger.error("Gagal mendapatkan daftar open circuits: %s", e)
                return []

    def allow(self, key: str) -> bool:
        """
        Periksa apakah permintaan ke resource 'key' diizinkan.
        """
        if not isinstance(key, str) or not key:
            logger.warning("allow() dipanggil dengan key tidak valid: %s", key)
            return False

        try:
            with self._lock:
                if key not in self._open_until:
                    return True
                if time.time() >= self._open_until[key]:
                    return True  # HALF_OPEN
                return False
        except Exception as e:
            logger.error("Error di allow(%s): %s", key, e)
            return False

    def record_failure(self, key: str):
        """Catat kegagalan. Jika mencapai threshold, buka sirkuit."""
        if not isinstance(key, str) or not key:
            logger.warning("record_failure() dipanggil dengan key tidak valid: %s", key)
            return

        try:
            with self._lock:
                self._failures[key] += 1
                if self._failures[key] >= self.threshold:
                    self._open_until[key] = time.time() + self.cooldown
                    logger.warning(
                        "Circuit Breaker OPEN untuk '%s' (%d kegagalan, cooldown %.0fs)",
                        key, self._failures[key], self.cooldown
                    )
        except Exception as e:
            logger.error("Error di record_failure(%s): %s", key, e)

    def record_success(self, key: str):
        """Catat keberhasilan. Tutup sirkuit (reset kegagalan)."""
        if not isinstance(key, str) or not key:
            logger.warning("record_success() dipanggil dengan key tidak valid: %s", key)
            return

        try:
            with self._lock:
                self._failures[key] = 0
                self._open_until.pop(key, None)
                logger.debug("Circuit Breaker CLOSED untuk '%s'", key)
        except Exception as e:
            logger.error("Error di record_success(%s): %s", key, e)

    def status(self, key: str) -> str:
        """Kembalikan status sirkuit untuk resource tertentu."""
        if not isinstance(key, str) or not key:
            return "INVALID_KEY"

        try:
            with self._lock:
                if key not in self._open_until:
                    return "CLOSED"
                if time.time() >= self._open_until[key]:
                    return "HALF_OPEN"
                return "OPEN"
        except Exception as e:
            logger.error("Error di status(%s): %s", key, e)
            return "ERROR"