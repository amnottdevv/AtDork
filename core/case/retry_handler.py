"""
Atdork – Retry Handler (core/case/retry_handler.py)
Menangani percobaan ulang cerdas dengan backoff eksponensial dan jitter.
"""

import time
import random
import logging
from typing import Callable, Any, Optional, Tuple
from core.case.error_classifier import ErrorCategory, classify_error

logger = logging.getLogger(__name__)


class RetryAbort(Exception):
    """
    Dilempar dari callback ``on_retry`` untuk menghentikan retry secara paksa.

    Dipakai oleh FallbackManager ketika keputusannya adalah ``ABORT`` (error
    fatal / semua resource terbuka). Tanpa exception khusus ini, keputusan
    abort tertelan oleh ``except`` umum dan retry tetap berjalan.
    """


class RetryHandler:
    """
    Menjalankan fungsi dengan mekanisme retry cerdas.

    Args:
        max_retries: Maksimal percobaan ulang.
        base_delay: Delay dasar dalam detik.
        max_delay: Delay maksimal dalam detik.
        jitter: Tambahkan jitter (acak) pada delay.
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        jitter: bool = True,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter

    def execute(
        self,
        func: Callable,
        *args,
        on_retry: Optional[Callable] = None,
        on_giveup: Optional[Callable] = None,
        **kwargs,
    ) -> Tuple[Any, Optional[Exception]]:
        """
        Jalankan fungsi dengan retry otomatis.

        Args:
            func: Fungsi yang akan dipanggil.
            *args: Argumen posisi untuk func.
            on_retry: Callback dipanggil sebelum retry (dengan argumen: attempt, exception).
            on_giveup: Callback dipanggil setelah menyerah (dengan argumen: exception).
            **kwargs: Argumen keyword untuk func.

        Returns:
            Tuple (hasil, None) jika sukses, atau (None, exception_terakhir) jika gagal.
        """
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                result = func(*args, **kwargs)
                return result, None
            except Exception as e:
                last_exception = e
                category = classify_error(e)

                # Jika error fatal, jangan retry
                if category == ErrorCategory.FATAL:
                    logger.error("Fatal error, not retrying: %s", e)
                    if on_giveup:
                        try:
                            on_giveup(e)
                        except Exception as cb_err:
                            logger.error("Error in on_giveup callback: %s", cb_err)
                    return None, e

                # Jika ini percobaan terakhir, menyerah
                if attempt >= self.max_retries:
                    logger.error("Max retries (%d) reached: %s", self.max_retries, e)
                    if on_giveup:
                        try:
                            on_giveup(e)
                        except Exception as cb_err:
                            logger.error("Error in on_giveup callback: %s", cb_err)
                    return None, e

                # Hitung delay
                delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                if self.jitter:
                    delay = delay * random.uniform(0.5, 1.5)

                logger.warning(
                    "Attempt %d/%d failed (%s), retrying in %.1fs...",
                    attempt + 1, self.max_retries, category, delay,
                )

                # Panggil callback on_retry jika ada
                if on_retry:
                    try:
                        on_retry(attempt + 1, e)
                    except RetryAbort as abort:
                        # Keputusan abort dari FallbackManager → berhenti, jangan retry.
                        logger.error("Retry aborted: %s", abort)
                        if on_giveup:
                            try:
                                on_giveup(abort)
                            except Exception as cb_err:
                                logger.error("Error in on_giveup callback: %s", cb_err)
                        return None, abort
                    except Exception as cb_err:
                        logger.error("Error in on_retry callback: %s", cb_err)

                time.sleep(delay)

        return None, last_exception