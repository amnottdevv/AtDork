"""
Atdork - Advanced Search Scanner
Professional-grade search module with error classification, backend fallback,
exponential backoff, and result validation.
"""

import time
import random
import logging
from typing import Optional, List, Dict, Any
from ddgs import DDGS
from core.user_agents_managements import get_random_user_agent

logger = logging.getLogger(__name__)


# ── Custom Exception Hierarchy ─────────────────────────────────────────────
class SearchError(Exception):
    """Base exception for all search failures."""
    pass


class RateLimitError(SearchError):
    """Raised when the search engine returns a rate-limit response (HTTP 429)."""
    pass


class BlockedError(SearchError):
    """Raised when the request is blocked (HTTP 403) or CAPTCHA is triggered."""
    pass


class ProxyError(SearchError):
    """Raised when a proxy connection fails."""
    pass


class ParseError(SearchError):
    """Raised when the response cannot be parsed correctly."""
    pass


class EmptyResultsError(SearchError):
    """Raised when the engine returns no usable results."""
    pass


# ── Fallback Backends ──────────────────────────────────────────────────────
FALLBACK_BACKENDS = [
    "duckduckgo",
    "bing",
    "brave",
    "mojeek",
    "startpage",
    "wikipedia",
]


# ── Helper Functions ───────────────────────────────────────────────────────
def _classify_error(exception: Exception, proxy: Optional[str] = None) -> SearchError:
    """
    Classify a raw exception into a specific SearchError subtype.
    This allows the retry logic to make smart decisions.
    """
    error_str = str(exception).lower()

    if any(keyword in error_str for keyword in ("rate", "429", "too many requests")):
        return RateLimitError(f"Rate limit detected: {exception}")
    elif any(keyword in error_str for keyword in ("block", "forbidden", "403", "captcha", "access denied")):
        return BlockedError(f"Blocked: {exception}")
    elif proxy and any(keyword in error_str for keyword in ("proxy", "socks", "connection refused", "tunnel")):
        return ProxyError(f"Proxy failure ({proxy}): {exception}")
    elif any(keyword in error_str for keyword in ("parse", "json", "html", "unexpected")):
        return ParseError(f"Parsing error: {exception}")
    else:
        return SearchError(f"Search error: {exception}")


def _validate_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Ensure every result has at least an 'href' field.
    If 'title' is missing, the URL is used as a placeholder.
    """
    valid = []
    for r in results:
        if not isinstance(r, dict):
            continue
        href = r.get("href")
        if href and href.strip():
            if not r.get("title"):
                r["title"] = href
            valid.append(r)
    return valid


# ── Main Search Function ───────────────────────────────────────────────────
def search_dork(
    query: str,
    max_results: int = 20,
    timeout: int = 10,
    retries: int = 2,
    delay: float = 0,
    proxy_manager=None,
    region: str = "us-en",
    safesearch: str = "moderate",
    timelimit: Optional[str] = None,
    backend: str = "auto",
    user_agent: Optional[str] = None,
    verify: bool = True,
    fallback_backends: bool = True,
) -> List[Dict[str, Any]]:
    """
    Execute a dork search with proxy rotation, backend fallback,
    exponential backoff with jitter, and result validation.

    Args:
        query: Search query string.
        max_results: Maximum number of results to return.
        timeout: Base timeout in seconds (increases per retry).
        retries: Maximum retry attempts per backend.
        delay: Delay between requests in seconds.
        proxy_manager: ProxyManager instance for proxy rotation.
        region: Search region/language code.
        safesearch: SafeSearch level ('on', 'moderate', 'off').
        timelimit: Time filter ('d','w','m','y').
        backend: Backend engine(s) – comma-separated or 'auto'.
        user_agent: Custom User-Agent string (None = auto-rotate).
        verify: SSL certificate verification (True/False or path to CA).
        fallback_backends: If True, try alternative backends on failure.

    Returns:
        List of result dicts with keys 'title', 'href', 'body'.

    Raises:
        SearchError: When all backends and retries are exhausted.
    """
    # ── User-Agent ─────────────────────────────────────────────────────
    if user_agent is None:
        user_agent = get_random_user_agent()
        logger.debug("Using random UA: %s...", user_agent[:60])

    # ── Build Backend Queue ────────────────────────────────────────────
    if backend == "auto" or not fallback_backends:
        backends_to_try = [backend]
    else:
        user_backends = [b.strip() for b in backend.split(",") if b.strip()]
        if len(user_backends) > 1:
            backends_to_try = user_backends
        else:
            backends_to_try = user_backends + [
                b for b in FALLBACK_BACKENDS if b not in user_backends
            ]

    last_error: Optional[SearchError] = None
    current_proxy: Optional[str] = None

    # ── Iterate Backends ───────────────────────────────────────────────
    for backend_name in backends_to_try:
        logger.info("Trying backend: %s", backend_name)

        for attempt in range(retries + 1):
            # ── Proxy Selection ──────────────────────────────────────────
            if proxy_manager:
                try:
                    current_proxy = proxy_manager.get_proxy()
                    if current_proxy is None and getattr(proxy_manager, '_strict', False):
                        raise ProxyError("No proxy available in strict mode")
                except RuntimeError as exc:
                    raise ProxyError(str(exc)) from exc
            else:
                current_proxy = None

            # ── Exponential Backoff with Jitter ──────────────────────────
            if attempt > 0:
                backoff = min(2 ** attempt + random.uniform(0, 1), 30)
                logger.debug("Backoff %.1fs before attempt %d", backoff, attempt + 1)
                time.sleep(backoff)

            # ── Progressive Timeout ─────────────────────────────────────
            current_timeout = timeout * (1 + attempt * 0.5)

            # ── Optional Pre‑Request Delay ─────────────────────────────
            if delay > 0:
                time.sleep(delay)

            try:
                # ── Execute Search ─────────────────────────────────────
                ddgs = DDGS(timeout=current_timeout, proxy=current_proxy, verify=verify)

                # Set custom User-Agent header
                try:
                    if hasattr(ddgs, 'session') and ddgs.session:
                        ddgs.session.headers.update({"User-Agent": user_agent})
                    elif hasattr(ddgs, 'headers'):
                        ddgs.headers = {"User-Agent": user_agent}
                except Exception as exc:
                    logger.debug("Unable to set UA header: %s", exc)

                start_time = time.time()
                with ddgs:
                    results = list(
                        ddgs.text(
                            query,
                            region=region,
                            safesearch=safesearch,
                            timelimit=timelimit,
                            max_results=max_results,
                            backend=backend_name,
                        )
                    )
                elapsed = time.time() - start_time
                logger.debug(
                    "Backend %s returned %d results in %.2fs",
                    backend_name, len(results), elapsed
                )

                # ── Validate & Normalise ──────────────────────────────
                results = _validate_results(results)
                if not results:
                    raise EmptyResultsError("No valid results returned")

                # ── Success ─────────────────────────────────────────────
                if proxy_manager:
                    proxy_manager.report_success(current_proxy)
                return results

            except EmptyResultsError:
                # Don't waste retries on empty results – try next backend
                last_error = EmptyResultsError("Backend returned empty results")
                logger.warning("Backend %s returned empty results, switching.", backend_name)
                break  # exit retry loop, go to next backend

            except Exception as exc:
                search_error = _classify_error(exc, current_proxy)
                last_error = search_error

                logger.warning(
                    "Attempt %d/%d failed [backend=%s, proxy=%s]: %s",
                    attempt + 1, retries + 1, backend_name, current_proxy, search_error
                )

                # Report failure to proxy manager
                if proxy_manager and current_proxy:
                    proxy_manager.report_failure(current_proxy)

                # Smart decision based on error type
                if isinstance(search_error, (RateLimitError, BlockedError)):
                    logger.info(
                        "Backend %s hit %s, switching to next backend.",
                        backend_name, type(search_error).__name__
                    )
                    break  # don't retry this backend

                if isinstance(search_error, ProxyError):
                    # Rotate UA as well, but keep same backend
                    user_agent = get_random_user_agent()
                    continue

                # For other errors, rotate UA and retry same backend
                user_agent = get_random_user_agent()

    # ── All Backends Exhausted ─────────────────────────────────────────
    raise SearchError(
        f"Failed to fetch results for query '{query[:50]}...' "
        f"after trying {len(backends_to_try)} backend(s) "
        f"with {retries + 1} attempt(s) each. "
        f"Last error: {last_error}"
    )
