"""
Atdork – Resilience Engine (Built‑in & Triggered)
Provides automatic fault‑tolerance for search operations.

Two protection levels:
  - Passive (always on) – basic retry + timeout escalation for transient errors
  - Active (--resilient) – circuit breaker, backend fallback, proxy rotation
"""

import time
import random
import logging
from typing import List, Dict, Optional, Tuple, Any
from collections import defaultdict

from core.scanner import search_dork, SearchError

logger = logging.getLogger(__name__)

# ── Error Classification ──────────────────────────────────────────────
class ErrorCategory:
    TRANSIENT   = "transient"     # temporary glitch → quick retry
    RATE_LIMIT  = "rate_limit"    # HTTP 429 → longer pause + circuit breaker
    BLOCKED     = "blocked"       # HTTP 403 → abandon backend
    PROXY_FAIL  = "proxy_fail"    # proxy dead → rotate
    FATAL       = "fatal"         # unrecoverable → abort immediately


def _classify_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if any(k in msg for k in ("429", "too many requests", "rate limit")):
        return ErrorCategory.RATE_LIMIT
    if any(k in msg for k in ("403", "forbidden", "blocked", "access denied")):
        return ErrorCategory.BLOCKED
    if any(k in msg for k in ("proxy", "socks", "connection refused", "tunnel")):
        return ErrorCategory.PROXY_FAIL
    if any(k in msg for k in ("timeout", "timed out", "connection error")):
        return ErrorCategory.TRANSIENT
    # scanner custom exceptions
    try:
        from core.scanner import RateLimitError, BlockedError, ProxyError
        if isinstance(exc, RateLimitError):
            return ErrorCategory.RATE_LIMIT
        if isinstance(exc, BlockedError):
            return ErrorCategory.BLOCKED
        if isinstance(exc, ProxyError):
            return ErrorCategory.PROXY_FAIL
    except ImportError:
        pass
    return ErrorCategory.FATAL


# ── Circuit Breaker ───────────────────────────────────────────────────
class CircuitBreaker:
    """Prevents hammering a failing backend/proxy."""
    def __init__(self, threshold: int = 3, cooldown: float = 120.0):
        self.threshold = threshold
        self.cooldown = cooldown
        self._failures: Dict[str, int] = defaultdict(int)
        self._open_until: Dict[str, float] = {}

    def allow(self, key: str) -> bool:
        return not (key in self._open_until and time.time() < self._open_until[key])

    def record_failure(self, key: str):
        self._failures[key] += 1
        if self._failures[key] >= self.threshold:
            self._open_until[key] = time.time() + self.cooldown
            logger.warning("Circuit BREAKER open for %s (%ds)", key, self.cooldown)

    def record_success(self, key: str):
        self._failures[key] = 0
        self._open_until.pop(key, None)


# ── Resilience Handler ────────────────────────────────────────────────
class ResilienceHandler:
    """
    Wraps search_dork with intelligent fault‑tolerance.

    Passive mode (default): up to 2 internal retries for transient errors,
        timeout increases each attempt.

    Active mode (--resilient): adds circuit breaker, backend fallback,
        proxy rotation, and longer cooldown periods.
    """

    def __init__(
        self,
        active: bool = False,
        max_retries: int = 2,
        backoff_base: float = 2.0,
        max_backoff: float = 30.0,
        circuit_threshold: int = 3,
        circuit_cooldown: float = 120.0,
        proxy_manager=None,
        fallback_backends: Optional[List[str]] = None,
    ):
        self.active = active
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.max_backoff = max_backoff
        self.proxy_manager = proxy_manager
        self.circuit_breaker = CircuitBreaker(circuit_threshold, circuit_cooldown) if active else None
        self.fallback_backends = fallback_backends or [
            "duckduckgo", "startpage", "yandex", "yahoo", "wikipedia"
        ]

        # stats
        self.stats = {"total": 0, "success": 0, "fail": 0, "retries": 0, "fallbacks": 0}

    # ── passive helper ────────────────────────────────────────────────
    def _passive_retry(self, attempt: int) -> float:
        """Backoff sederhana untuk transient error."""
        if attempt == 0:
            return 0.0
        return min(self.backoff_base ** attempt + random.uniform(0, 1), self.max_backoff)

    # ── main executor ─────────────────────────────────────────────────
    def execute(
        self, query: str, **search_kwargs
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        """
        Execute a single search query with resilience.

        Returns: (results, error_message)  – error_message is None on success.
        """
        self.stats["total"] += 1
        backend = search_kwargs.pop("backend", "auto")

        # ── active mode: expand backend list ────────────────────────
        if self.active and backend == "auto":
            backends_to_try = self.fallback_backends
        else:
            backends_to_try = [backend]

        last_error = None
        current_proxy = None

        for bname in backends_to_try:
            # circuit breaker check (active only)
            if self.circuit_breaker and not self.circuit_breaker.allow(bname):
                logger.info("Backend %s is OPEN – skipping", bname)
                continue

            for attempt in range(self.max_retries + 1):
                # proxy selection
                if self.proxy_manager:
                    try:
                        current_proxy = self.proxy_manager.get_proxy()
                    except RuntimeError:
                        current_proxy = None
                else:
                    current_proxy = None

                # circuit breaker for proxy (active only)
                if self.circuit_breaker and current_proxy and not self.circuit_breaker.allow(current_proxy):
                    logger.info("Proxy %s is OPEN – skipping", current_proxy)
                    continue

                # backoff
                if self.active:
                    if attempt > 0:
                        backoff = min(self.backoff_base ** attempt + random.uniform(0, 1), self.max_backoff)
                        time.sleep(backoff)
                else:
                    backoff = self._passive_retry(attempt)
                    if backoff > 0:
                        time.sleep(backoff)

                try:
                    results = search_dork(
                        query,
                        backend=bname,
                        proxy_manager=self.proxy_manager,
                        **search_kwargs,
                    )
                    # success
                    self.stats["success"] += 1
                    if self.circuit_breaker:
                        self.circuit_breaker.record_success(bname)
                        if current_proxy:
                            self.circuit_breaker.record_success(current_proxy)
                    return results, None

                except Exception as exc:
                    last_error = exc
                    category = _classify_error(exc)
                    self.stats["retries"] += 1

                    # circuit breaker recording (active only)
                    if self.circuit_breaker:
                        if category in (ErrorCategory.RATE_LIMIT, ErrorCategory.BLOCKED):
                            self.circuit_breaker.record_failure(bname)
                        elif category == ErrorCategory.PROXY_FAIL and current_proxy:
                            self.circuit_breaker.record_failure(current_proxy)

                    # decision logic
                    if category == ErrorCategory.FATAL:
                        self.stats["fail"] += 1
                        return None, str(exc)

                    if category == ErrorCategory.BLOCKED:
                        # don't retry same backend
                        break

                    if category == ErrorCategory.RATE_LIMIT:
                        if self.active:
                            break   # try next backend
                        else:
                            time.sleep(self.max_backoff)
                            continue

                    if category == ErrorCategory.PROXY_FAIL:
                        if self.proxy_manager:
                            self.proxy_manager.report_failure(current_proxy)
                        # retry with next proxy
                        continue

                    # transient → retry if attempts remain
                    if attempt == self.max_retries:
                        break

            # if we exit the retry loop, try next backend
            self.stats["fallbacks"] += 1
            logger.info("Switching backend after %s", bname)

        # all exhausted
        self.stats["fail"] += 1
        return None, f"All backends exhausted for '{query[:50]}...' Last: {last_error}"


# ── Convenience function ──────────────────────────────────────────────
def resilient_search(query: str, active: bool = False, **kwargs) -> List[Dict[str, Any]]:
    """Single-call resilient search. Set active=True for full protection."""
    handler = ResilienceHandler(active=active)
    results, err = handler.execute(query, **kwargs)
    if err:
        raise RuntimeError(err)
    return results
