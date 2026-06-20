"""
Atdork – Stats Collector (core/case/stats.py)
Mengumpulkan dan menampilkan statistik runtime dari semua handler case.
"""

import time
import threading
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class StatsCollector:
    """
    Mengumpulkan statistik runtime untuk dianalisis dan ditampilkan.

    Meliputi:
    - Statistik backend (request, sukses, rate-limit, dll.)
    - Statistik proxy (aktif, banned, sukses, gagal)
    - Statistik fallback (total, sukses, gagal)
    - Statistik retry (total, sukses, gagal)
    - Statistik circuit breaker (total terbuka)
    - Statistik IP Guard (pengecekan, kebocoran)
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.start_time = time.time()

        # Backend stats
        self.backends: Dict[str, Dict[str, int]] = {}

        # Proxy stats
        self.proxies: Dict[str, Dict[str, int]] = {
            "active": 0,
            "banned": 0,
            "removed": 0,
            "total_success": 0,
            "total_failure": 0,
        }

        # Fallback stats
        self.fallbacks: Dict[str, int] = {
            "total_triggered": 0,
            "successful": 0,
            "failed": 0,
        }

        # Retry stats
        self.retries: Dict[str, int] = {
            "total_attempted": 0,
            "successful": 0,
            "failed": 0,
        }

        # Circuit breaker stats
        self.circuit_breaker_stats: Dict[str, int] = {
            "total_opened": 0,
        }

        # IP Guard stats
        self.ip_guard_stats: Dict[str, int] = {
            "checks_performed": 0,
            "leaks_detected": 0,
        }

    def record_backend(self, backend: str, status_code: int, has_results: bool):
        """Catat respons backend."""
        with self._lock:
            try:
                if backend not in self.backends:
                    self.backends[backend] = {
                        "total_requests": 0,
                        "success": 0,
                        "rate_limited": 0,
                        "blocked": 0,
                        "empty": 0,
                    }
                stats = self.backends[backend]
                stats["total_requests"] += 1
                if status_code == 200 and has_results:
                    stats["success"] += 1
                elif status_code == 429:
                    stats["rate_limited"] += 1
                elif status_code == 403:
                    stats["blocked"] += 1
                elif status_code == 200 and not has_results:
                    stats["empty"] += 1
            except Exception as e:
                logger.error("Error recording backend stat: %s", e)

    def record_proxy(self, active: int, banned: int, removed: int, success: int, failure: int):
        """Perbarui statistik proxy."""
        with self._lock:
            try:
                self.proxies["active"] = active
                self.proxies["banned"] = banned
                self.proxies["removed"] = removed
                self.proxies["total_success"] += success
                self.proxies["total_failure"] += failure
            except Exception as e:
                logger.error("Error recording proxy stat: %s", e)

    def record_fallback(self, success: bool):
        """Catat hasil fallback."""
        with self._lock:
            try:
                self.fallbacks["total_triggered"] += 1
                if success:
                    self.fallbacks["successful"] += 1
                else:
                    self.fallbacks["failed"] += 1
            except Exception as e:
                logger.error("Error recording fallback stat: %s", e)

    def record_retry(self, success: bool):
        """Catat hasil retry."""
        with self._lock:
            try:
                self.retries["total_attempted"] += 1
                if success:
                    self.retries["successful"] += 1
                else:
                    self.retries["failed"] += 1
            except Exception as e:
                logger.error("Error recording retry stat: %s", e)

    def record_circuit_breaker(self, opened: bool = False):
        """Catat pembukaan circuit breaker."""
        with self._lock:
            try:
                if opened:
                    self.circuit_breaker_stats["total_opened"] += 1
            except Exception as e:
                logger.error("Error recording circuit breaker stat: %s", e)

    def record_ip_guard(self, check: bool = False, leak: bool = False):
        """Catat aktivitas IP Guard."""
        with self._lock:
            try:
                if check:
                    self.ip_guard_stats["checks_performed"] += 1
                if leak:
                    self.ip_guard_stats["leaks_detected"] += 1
            except Exception as e:
                logger.error("Error recording IP guard stat: %s", e)

    def summary(self) -> str:
        """Hasilkan ringkasan statistik yang siap ditampilkan."""
        elapsed = time.time() - self.start_time
        lines = []
        lines.append("═" * 55)
        lines.append("  AtDork Runtime Statistics")
        lines.append("═" * 55)
        lines.append(f"  Total runtime: {elapsed:.1f}s")
        lines.append("")

        # Backend
        if self.backends:
            lines.append("🔄 BACKENDS")
            for name, stats in self.backends.items():
                lines.append(
                    f"   {name:<12} | Req: {stats['total_requests']:<4} | "
                    f"OK: {stats['success']:<3} | 429: {stats['rate_limited']:<3} | "
                    f"403: {stats['blocked']:<3}"
                )
            lines.append("")

        # Proxy
        lines.append("🛡️ PROXIES")
        lines.append(
            f"   Active: {self.proxies['active']} | "
            f"Banned: {self.proxies['banned']} | "
            f"Removed: {self.proxies['removed']}"
        )
        lines.append(
            f"   Success: {self.proxies['total_success']} | "
            f"Failure: {self.proxies['total_failure']}"
        )
        lines.append("")

        # Fallback
        lines.append("🔁 FALLBACKS")
        lines.append(
            f"   Triggered: {self.fallbacks['total_triggered']} | "
            f"Successful: {self.fallbacks['successful']} | "
            f"Failed: {self.fallbacks['failed']}"
        )
        lines.append("")

        # Retry
        lines.append("🔄 RETRIES")
        lines.append(
            f"   Attempted: {self.retries['total_attempted']} | "
            f"Successful: {self.retries['successful']} | "
            f"Failed: {self.retries['failed']}"
        )
        lines.append("")

        # Circuit Breaker
        lines.append("⚡ CIRCUIT BREAKER")
        lines.append(f"   Total opened: {self.circuit_breaker_stats['total_opened']}")
        lines.append("")

        # IP Guard
        lines.append("🛡️ IP GUARD")
        lines.append(
            f"   Checks: {self.ip_guard_stats['checks_performed']} | "
            f"Leaks: {self.ip_guard_stats['leaks_detected']}"
        )
        lines.append("═" * 55)

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Ekspor semua statistik sebagai dictionary (untuk JSON/CSV)."""
        with self._lock:
            return {
                "runtime_seconds": time.time() - self.start_time,
                "backends": dict(self.backends),
                "proxies": dict(self.proxies),
                "fallbacks": dict(self.fallbacks),
                "retries": dict(self.retries),
                "circuit_breaker": dict(self.circuit_breaker_stats),
                "ip_guard": dict(self.ip_guard_stats),
            }