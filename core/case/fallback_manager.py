"""
Atdork – Fallback Manager (core/case/fallback_manager.py)
Memutuskan tindakan terbaik saat terjadi kegagalan berdasarkan
kategori error, status circuit breaker, dan ketersediaan resource.
"""

import logging
from typing import Optional, List, Dict, Any

from core.case.error_classifier import ErrorCategory
from core.case.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class FallbackAction:
    """Konstanta tindakan yang bisa diambil oleh FallbackManager."""
    CONTINUE        = "continue"          # lanjutkan tanpa perubahan
    RETRY           = "retry"             # coba lagi dengan resource yang sama
    SWITCH_BACKEND  = "switch_backend"    # ganti backend pencarian
    ROTATE_PROXY    = "rotate_proxy"      # ganti proxy
    COOLDOWN        = "cooldown"          # jeda panjang, lalu coba lagi
    ABORT           = "abort"             # hentikan (tidak bisa dipulihkan)


class FallbackManager:
    """
    Mengelola fallback backend dan proxy secara cerdas.

    Args:
        backends: Daftar backend yang tersedia (misal ["google", "duckduckgo", "startpage"]).
        circuit_breaker: Instance CircuitBreaker yang sudah dikonfigurasi.
        proxy_manager: Instance ProxyManager (opsional).
    """

    def __init__(
        self,
        backends: List[str],
        circuit_breaker: CircuitBreaker,
        proxy_manager=None
    ):
        if not backends:
            raise ValueError("Daftar backend tidak boleh kosong")
        if not circuit_breaker:
            raise ValueError("CircuitBreaker wajib disediakan")

        self.backends = backends
        self.circuit_breaker = circuit_breaker
        self.proxy_manager = proxy_manager

    def _get_healthy_backend(self, exclude: Optional[str] = None) -> Optional[str]:
        """Cari backend yang tidak sedang dalam status OPEN."""
        for b in self.backends:
            if b != exclude and self.circuit_breaker.allow(b):
                return b
        return None

    def _get_healthy_proxy(self) -> Optional[str]:
        """Ambil proxy yang sehat dari proxy_manager."""
        if not self.proxy_manager:
            return None
        try:
            return self.proxy_manager.get_proxy()
        except Exception as e:
            logger.warning("Gagal mengambil proxy: %s", e)
            return None

    def decide(
        self,
        current_backend: str,
        current_proxy: Optional[str],
        error_category: str,
        has_results: bool = False,
    ) -> Dict[str, Any]:
        """
        Putuskan tindakan yang harus diambil setelah menerima error.

        Args:
            current_backend: Backend yang sedang digunakan.
            current_proxy: Proxy yang sedang digunakan (None jika tidak pakai proxy).
            error_category: Kategori error (dari ErrorCategory).
            has_results: Apakah respons mengandung hasil parsial?

        Returns:
            Dictionary dengan kunci:
                - action (str): salah satu FallbackAction
                - next_backend (str|None): backend yang disarankan
                - next_proxy (str|None): proxy yang disarankan
                - reason (str): alasan keputusan
        """
        result = {
            "action": FallbackAction.ABORT,
            "next_backend": None,
            "next_proxy": None,
            "reason": "",
        }

        try:
            # 1. Rate limit → cooldown backend, ganti backend
            if error_category == ErrorCategory.RATE_LIMIT:
                self.circuit_breaker.record_failure(current_backend)
                healthy = self._get_healthy_backend(exclude=current_backend)
                if healthy:
                    result["action"] = FallbackAction.SWITCH_BACKEND
                    result["next_backend"] = healthy
                    result["reason"] = f"Backend {current_backend} rate‑limited, beralih ke {healthy}"
                else:
                    result["action"] = FallbackAction.COOLDOWN
                    result["reason"] = f"Semua backend rate‑limited, cooldown diperlukan"
                return result

            # 2. Blocked → ganti backend + rotasi proxy
            if error_category == ErrorCategory.BLOCKED:
                self.circuit_breaker.record_failure(current_backend)
                if current_proxy:
                    self.circuit_breaker.record_failure(current_proxy)
                    if self.proxy_manager:
                        self.proxy_manager.report_failure(current_proxy)
                healthy_backend = self._get_healthy_backend(exclude=current_backend)
                healthy_proxy = self._get_healthy_proxy()
                result["action"] = FallbackAction.SWITCH_BACKEND
                result["next_backend"] = healthy_backend or self.backends[0]
                result["next_proxy"] = healthy_proxy
                result["reason"] = f"Backend {current_backend} memblokir, beralih"
                return result

            # 3. Proxy fail → rotasi proxy
            if error_category == ErrorCategory.PROXY_FAIL:
                if current_proxy:
                    self.circuit_breaker.record_failure(current_proxy)
                    if self.proxy_manager:
                        self.proxy_manager.report_failure(current_proxy)
                healthy_proxy = self._get_healthy_proxy()
                if healthy_proxy:
                    result["action"] = FallbackAction.ROTATE_PROXY
                    result["next_proxy"] = healthy_proxy
                    result["reason"] = "Proxy gagal, rotasi ke proxy lain"
                else:
                    result["action"] = FallbackAction.COOLDOWN
                    result["reason"] = "Semua proxy gagal, cooldown diperlukan"
                return result

            # 4. Transient → retry
            if error_category == ErrorCategory.TRANSIENT:
                result["action"] = FallbackAction.RETRY
                result["reason"] = "Error sementara, retry"
                return result

            # 5. Fatal → abort
            result["action"] = FallbackAction.ABORT
            result["reason"] = f"Error fatal: tidak dapat dipulihkan"
            return result

        except Exception as e:
            logger.error("Error di FallbackManager.decide(): %s", e)
            result["action"] = FallbackAction.ABORT
            result["reason"] = f"Kesalahan internal FallbackManager: {e}"
            return result