"""
Atdork – Recovery Strategy (core/case/recovery_strategy.py)
Peta strategi pemulihan untuk setiap kategori error.
"""

import logging
from typing import Optional, Dict, Any
from atdork.core.case.error_classifier import ErrorCategory
from atdork.core.case.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class RecoveryAction:
    """Konstanta tindakan pemulihan."""
    RETRY_WITH_BACKOFF = "retry_with_backoff"
    SWITCH_BACKEND = "switch_backend"
    ROTATE_PROXY = "rotate_proxy"
    LONG_COOLDOWN = "long_cooldown"
    ABORT = "abort"


class RecoveryStrategy:
    """
    Memetakan ErrorCategory ke tindakan pemulihan yang disarankan.

    Dapat diintegrasikan dengan FallbackManager untuk memberikan
    keputusan yang lebih kaya (misal: retry dulu, baru fallback).
    """

    def __init__(self, circuit_breaker: CircuitBreaker):
        self.circuit_breaker = circuit_breaker

    def get_action(
        self,
        error_category: str,
        backend: str,
        proxy: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Dapatkan tindakan pemulihan berdasarkan kategori error.

        Args:
            error_category: Kategori error (dari ErrorCategory).
            backend: Backend yang sedang digunakan.
            proxy: Proxy yang sedang digunakan (opsional).

        Returns:
            Dictionary dengan kunci:
                - action (str): salah satu RecoveryAction
                - metadata (dict): informasi tambahan (misal alasan, saran)
        """
        result = {
            "action": RecoveryAction.ABORT,
            "metadata": {},
        }

        try:
            if error_category == ErrorCategory.TRANSIENT:
                result["action"] = RecoveryAction.RETRY_WITH_BACKOFF
                result["metadata"]["reason"] = "Error sementara, coba lagi dengan jeda."

            elif error_category == ErrorCategory.RATE_LIMIT:
                self.circuit_breaker.record_failure(backend)
                result["action"] = RecoveryAction.SWITCH_BACKEND
                result["metadata"]["reason"] = (
                    f"Backend {backend} terkena rate limit. Beralih ke backend lain."
                )

            elif error_category == ErrorCategory.BLOCKED:
                self.circuit_breaker.record_failure(backend)
                if proxy:
                    self.circuit_breaker.record_failure(proxy)
                result["action"] = RecoveryAction.SWITCH_BACKEND
                result["metadata"]["reason"] = (
                    f"Backend {backend} memblokir permintaan. Ganti backend dan/atau proxy."
                )

            elif error_category == ErrorCategory.PROXY_FAIL:
                if proxy:
                    self.circuit_breaker.record_failure(proxy)
                result["action"] = RecoveryAction.ROTATE_PROXY
                result["metadata"]["reason"] = "Proxy gagal. Rotasi ke proxy lain."

            elif error_category == ErrorCategory.FATAL:
                result["action"] = RecoveryAction.ABORT
                result["metadata"]["reason"] = "Error fatal, tidak dapat dipulihkan."

            else:
                result["action"] = RecoveryAction.ABORT
                result["metadata"]["reason"] = f"Kategori error tidak dikenal: {error_category}"

        except Exception as e:
            logger.error("Error di RecoveryStrategy.get_action(): %s", e)
            result["action"] = RecoveryAction.ABORT
            result["metadata"]["reason"] = f"Kesalahan internal RecoveryStrategy: {e}"

        return result
