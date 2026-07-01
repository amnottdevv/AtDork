"""
Atdork – Adaptive Delay (core/case/adaptive_delay.py)
Delay yang menyesuaikan diri berdasarkan respons backend.
"""

import time
import threading
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class AdaptiveDelay:
    """
    Mengatur delay antar permintaan secara adaptif per backend.

    Args:
        base_delay: Delay awal dalam detik.
        max_delay: Delay maksimal dalam detik.
        backoff_factor: Faktor pengali saat terkena rate-limit.
        recovery_factor: Faktor pengali saat sukses (pemulihan bertahap).
        min_delay: Delay minimal dalam detik.
        history_size: Jumlah respons terakhir yang diingat per backend.
    """

    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
        recovery_factor: float = 0.9,
        min_delay: float = 0.1,
        history_size: int = 100,
    ):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.recovery_factor = recovery_factor
        self.min_delay = min_delay
        self.history_size = history_size

        self._delays: Dict[str, float] = {}
        self._last_request: Dict[str, float] = {}
        self._history: Dict[str, list] = {}
        self._lock = threading.Lock()

    def _ensure_backend(self, backend: str):
        """Inisialisasi data untuk backend jika belum ada."""
        if backend not in self._delays:
            self._delays[backend] = self.base_delay
        if backend not in self._last_request:
            self._last_request[backend] = 0.0
        if backend not in self._history:
            self._history[backend] = []

    def wait(self, backend: str):
        """
        Tunggu sesuai delay yang diperlukan untuk backend tertentu.
        """
        with self._lock:
            self._ensure_backend(backend)
            now = time.time()
            elapsed = now - self._last_request[backend]
            required = self._delays[backend]
            wait_time = max(0.0, required - elapsed)

        if wait_time > 0:
            logger.debug("AdaptiveDelay: menunggu %.2fs untuk %s", wait_time, backend)
            time.sleep(wait_time)

        with self._lock:
            self._last_request[backend] = time.time()

    def report(self, backend: str, status_code: int, has_results: bool):
        """
        Laporkan hasil permintaan untuk menyesuaikan delay.

        Args:
            backend: Nama backend.
            status_code: Kode status HTTP.
            has_results: Apakah respons mengandung hasil.
        """
        with self._lock:
            self._ensure_backend(backend)

            # Catat riwayat
            self._history[backend].append((time.time(), status_code, has_results))
            if len(self._history[backend]) > self.history_size:
                self._history[backend] = self._history[backend][-self.history_size:]

            old_delay = self._delays[backend]

            try:
                if status_code == 429 or (status_code == 202 and not has_results):
                    # Rate-limit → naikkan delay
                    new_delay = min(old_delay * self.backoff_factor, self.max_delay)
                    self._delays[backend] = new_delay
                    logger.info(
                        "AdaptiveDelay: %s delay naik %.2fs → %.2fs (rate limit)",
                        backend, old_delay, new_delay,
                    )
                elif status_code == 200 and has_results:
                    # Sukses → turunkan delay bertahap
                    new_delay = max(old_delay * self.recovery_factor, self.min_delay)
                    if new_delay < old_delay:
                        self._delays[backend] = new_delay
                        logger.debug(
                            "AdaptiveDelay: %s delay turun %.2fs → %.2fs (success)",
                            backend, old_delay, new_delay,
                        )
            except Exception as e:
                logger.error("Error saat menyesuaikan delay untuk %s: %s", backend, e)

    def get_delay(self, backend: str) -> float:
        """Dapatkan delay saat ini untuk backend."""
        with self._lock:
            self._ensure_backend(backend)
            return self._delays[backend]

    def recommendation(self, backend: str) -> str:
        """Berikan saran delay optimal berdasarkan riwayat."""
        with self._lock:
            self._ensure_backend(backend)
            history = self._history[backend]
            delay = self._delays[backend]

            if not history:
                return f"Backend '{backend}': belum ada data."

            total = len(history)
            rate_limited = sum(1 for _, sc, _ in history if sc == 429)
            success = sum(1 for _, sc, hr in history if sc == 200 and hr)
            success_rate = (success / total * 100) if total > 0 else 0

            if rate_limited > 0 and success_rate < 50:
                suggested = min(delay * 1.5, self.max_delay)
                return (
                    f"Backend '{backend}': {rate_limited}/{total} rate-limited, "
                    f"success rate {success_rate:.0f}%. "
                    f"Current delay: {delay:.2f}s. "
                    f"Recommendation: increase delay to at least {suggested:.2f}s "
                    f"or switch backend."
                )
            elif rate_limited > 0:
                return (
                    f"Backend '{backend}': {rate_limited}/{total} rate-limited, "
                    f"but success rate still {success_rate:.0f}%. "
                    f"Current delay: {delay:.2f}s. Keep monitoring."
                )
            elif success_rate < 30:
                return (
                    f"Backend '{backend}': success rate {success_rate:.0f}%, "
                    f"no rate-limits. Delay: {delay:.2f}s. "
                    f"Possible backend issues, consider fallback."
                )
            else:
                return (
                    f"Backend '{backend}': success rate {success_rate:.0f}%, "
                    f"delay {delay:.2f}s. Everything looks healthy."
                )

    def all_recommendations(self) -> Dict[str, str]:
        """Dapatkan saran untuk semua backend."""
        with self._lock:
            backends = list(self._delays.keys())
        result = {}
        for b in backends:
            try:
                result[b] = self.recommendation(b)
            except Exception as e:
                result[b] = f"Error generating recommendation: {e}"
        return result

    def reset(self, backend: str):
        """Reset delay untuk backend ke nilai dasar."""
        with self._lock:
            self._delays[backend] = self.base_delay
            self._last_request[backend] = 0.0
            logger.info("AdaptiveDelay: %s direset ke %.2fs", backend, self.base_delay)
