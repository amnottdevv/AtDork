"""
Atdork – Adaptive Rate Limiter (core/case/rate_limiter.py)
Mengelola laju permintaan ke berbagai backend secara otomatis.

Fitur:
- Delay per backend yang disesuaikan secara adaptif berdasarkan respons.
- Thread‑safe.
- Mencatat riwayat status untuk analisis.
- Memberikan saran delay optimal setelah pengamatan.
"""

import time
import threading
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Default values
DEFAULT_BASE_DELAY = 1.0
DEFAULT_MAX_DELAY = 60.0
DEFAULT_BACKOFF_FACTOR = 2.0
DEFAULT_RECOVERY_FACTOR = 0.9
DEFAULT_MIN_DELAY = 0.1
DEFAULT_HISTORY_LENGTH = 100  # jumlah respons terakhir yang diingat per backend


class RateLimiter:
    """
    Adaptive rate limiter per backend.

    Setiap backend memiliki delay dinamis yang naik saat terkena rate‑limit
    dan turun secara perlahan saat permintaan berhasil.

    Selain itu, modul ini mencatat riwayat respons dan dapat memberikan
    saran akhir tentang delay yang disarankan.
    """

    def __init__(
        self,
        base_delay: float = DEFAULT_BASE_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        recovery_factor: float = DEFAULT_RECOVERY_FACTOR,
        min_delay: float = DEFAULT_MIN_DELAY,
        history_length: int = DEFAULT_HISTORY_LENGTH,
    ):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.recovery_factor = recovery_factor
        self.min_delay = min_delay
        self.history_length = history_length

        # Data per backend
        self._delays: Dict[str, float] = {}
        self._last_request_time: Dict[str, float] = {}
        self._history: Dict[str, List[Tuple[float, int, bool]]] = {}  # (timestamp, status_code, has_results)
        self._lock = threading.Lock()

    def _ensure_backend(self, backend: str):
        if backend not in self._delays:
            self._delays[backend] = self.base_delay
        if backend not in self._last_request_time:
            self._last_request_time[backend] = 0.0
        if backend not in self._history:
            self._history[backend] = []

    def get_delay(self, backend: str) -> float:
        """Dapatkan delay saat ini untuk backend tertentu (tanpa menunggu)."""
        with self._lock:
            self._ensure_backend(backend)
            return self._delays[backend]

    def wait(self, backend: str):
        """Tunggu sesuai delay yang diperlukan untuk backend tertentu."""
        with self._lock:
            self._ensure_backend(backend)
            now = time.time()
            elapsed = now - self._last_request_time[backend]
            required_delay = self._delays[backend]
            wait_time = max(0.0, required_delay - elapsed)

        if wait_time > 0:
            logger.debug("Rate limiter: waiting %.2fs for backend %s", wait_time, backend)
            time.sleep(wait_time)

        with self._lock:
            self._last_request_time[backend] = time.time()

    def report_response(self, backend: str, status_code: int, has_results: bool):
        """
        Laporkan hasil permintaan untuk menyesuaikan delay secara adaptif.

        - status 429 atau (202 tanpa hasil) → delay dinaikkan.
        - sukses (200 dengan hasil) → delay diturunkan bertahap.
        - Kasus lain tidak mengubah delay.
        """
        with self._lock:
            self._ensure_backend(backend)

            # Simpan riwayat
            self._history[backend].append((time.time(), status_code, has_results))
            if len(self._history[backend]) > self.history_length:
                self._history[backend] = self._history[backend][-self.history_length:]

            if status_code == 429 or (status_code == 202 and not has_results):
                old_delay = self._delays[backend]
                new_delay = min(old_delay * self.backoff_factor, self.max_delay)
                self._delays[backend] = new_delay
                logger.info(
                    "Rate limiter: backend %s delay increased %.2fs → %.2fs (rate limit)",
                    backend, old_delay, new_delay
                )
            elif status_code == 200 and has_results:
                old_delay = self._delays[backend]
                new_delay = max(old_delay * self.recovery_factor, self.min_delay)
                if new_delay < old_delay:
                    self._delays[backend] = new_delay
                    logger.debug(
                        "Rate limiter: backend %s delay decreased %.2fs → %.2fs (success)",
                        backend, old_delay, new_delay
                    )

    def get_stats(self, backend: str) -> Dict[str, float]:
        """Dapatkan statistik dasar untuk backend tertentu."""
        with self._lock:
            self._ensure_backend(backend)
            history = self._history[backend]
            total = len(history)
            if total == 0:
                return {"total_requests": 0, "success_rate": 0.0, "rate_limited": 0, "current_delay": self._delays[backend]}

            rate_limited = sum(1 for _, code, has_res in history if code == 429 or (code == 202 and not has_res))
            success = sum(1 for _, code, has_res in history if code == 200 and has_res)
            return {
                "total_requests": total,
                "success_rate": success / total if total > 0 else 0.0,
                "rate_limited": rate_limited,
                "current_delay": self._delays[backend],
            }

    def get_recommendation(self, backend: str) -> str:
        """
        Berikan saran akhir tentang backend berdasarkan riwayat.
        """
        stats = self.get_stats(backend)
        if stats["total_requests"] == 0:
            return f"No data for backend '{backend}' yet."

        delay = stats["current_delay"]
        success_rate = stats["success_rate"] * 100
        rate_limited = stats["rate_limited"]
        total = stats["total_requests"]

        if rate_limited > 0 and success_rate < 50:
            suggested = min(delay * 1.5, self.max_delay)
            return (
                f"Backend '{backend}': {rate_limited}/{total} rate‑limited, "
                f"success rate {success_rate:.0f}%. "
                f"Current delay: {delay:.2f}s. "
                f"Recommendation: increase delay to at least {suggested:.2f}s "
                f"or switch backend."
            )
        elif rate_limited > 0:
            return (
                f"Backend '{backend}': {rate_limited}/{total} rate‑limited, "
                f"but success rate still {success_rate:.0f}%. "
                f"Current delay: {delay:.2f}s. Keep monitoring."
            )
        elif success_rate < 30:
            return (
                f"Backend '{backend}': success rate {success_rate:.0f}%, "
                f"no rate‑limits. Delay: {delay:.2f}s. "
                f"Possible backend issues, consider fallback."
            )
        else:
            return (
                f"Backend '{backend}': success rate {success_rate:.0f}%, "
                f"delay {delay:.2f}s. Everything looks healthy."
            )

    def all_recommendations(self) -> Dict[str, str]:
        """Dapatkan saran untuk semua backend yang pernah digunakan."""
        with self._lock:
            backends = list(self._delays.keys())
        return {b: self.get_recommendation(b) for b in backends}
