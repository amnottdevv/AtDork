"""
Atdork - Advanced Search Scanner
Professional-grade search module with error classification, backend fallback,
exponential backoff, result validation, and credential-safe logging.
"""

import time
import random
import logging
from typing import Optional, List, Dict, Any
from ddgs import DDGS
from core.providers import ProviderError, get_provider
from core.user_agents_managements import get_random_user_agent
from lib.redactor import redact_proxy_url

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


class QuotaExceededError(RateLimitError):
    """A third-party API ran out of credits/quota — treated as a rate limit
    (skip this backend, let the fallback chain continue).

    The message intentionally contains 'rate limit' so the message-based
    case/error_classifier maps it to RATE_LIMIT as well.
    """
    pass


class AuthError(BlockedError):
    """API key rejected (HTTP 401/403 auth) — skip this backend."""
    pass


class ProviderConfigError(SearchError):
    """Provider configured but unusable (missing api_key, unknown provider)."""
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


# ── Backend queue / provider helpers ───────────────────────────────────────
def _normalize_chain(chain) -> Optional[List[str]]:
    """Accept 'a,b' or ['a', 'b'] → clean list (None when empty/absent)."""
    if isinstance(chain, str):
        items = [b.strip() for b in chain.split(",") if b.strip()]
    elif isinstance(chain, (list, tuple)):
        items = [str(b).strip() for b in chain if str(b).strip()]
    else:
        return None
    return items or None


def _config_section(name: str) -> Dict[str, Any]:
    """Read a nested config section ({} when config not loaded / not a dict)."""
    try:
        from core.config import get_setting
        section = get_setting(name)
    except Exception:  # pragma: no cover - config module always importable
        return {}
    return section if isinstance(section, dict) else {}


def resolve_backend_queue(
    backend: str,
    fallback_backends: bool = True,
    chain: Optional[List[str]] = None,
    profiles: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Build the ordered list of backends to try.

    - `profiles` maps names to explicit chains; `--backend <profile>` expands
      to that chain regardless of the fallback flag (an explicit choice).
    - `backend == 'auto'` stays first; a configured `search.fallback` chain is
      appended so API providers (serper/serpapi/brave) can catch failures.
    - Comma lists are honoured as-is (original behaviour).
    - Otherwise the configured chain (or FALLBACK_BACKENDS) is appended.
    """
    if profiles and isinstance(backend, str) and backend in profiles:
        named = _normalize_chain(profiles[backend])
        if named:
            return list(dict.fromkeys(named))

    if backend == "auto":
        queue = ["auto"]
        if fallback_backends and chain:
            queue = queue + [b for b in dict.fromkeys(chain) if b != "auto"]
        return queue

    if not fallback_backends:
        return [backend]

    user_backends = [b.strip() for b in backend.split(",") if b.strip()]
    if len(user_backends) > 1:
        return user_backends

    base = list(chain) if chain else list(FALLBACK_BACKENDS)
    return user_backends + [b for b in base if b not in user_backends]


def _translate_provider_error(pe: Exception) -> SearchError:
    """Map a ProviderError (kind=...) onto the SearchError hierarchy."""
    kind = getattr(pe, "kind", "api")
    msg = str(pe)
    if kind == "quota":
        return QuotaExceededError(f"API quota exceeded (rate limit): {msg}")
    if kind == "rate_limit":
        return RateLimitError(f"Rate limited: {msg}")
    if kind == "auth":
        return AuthError(f"Authentication failed: {msg}")
    if kind == "config":
        return ProviderConfigError(msg)
    if kind == "blocked":
        return BlockedError(msg)
    if kind == "parse":
        return ParseError(msg)
    return SearchError(msg)


# ── Helper Functions ───────────────────────────────────────────────────────
def _classify_error(exception: Exception, proxy: Optional[str] = None) -> SearchError:
    """
    Classify a raw exception into a specific SearchError subtype.
    This allows the retry logic to make smart decisions.
    """
    error_str = str(exception).lower()

    # ddgs 9.x melempar DDGSException("No results found.") untuk query tanpa
    # hasil — itu bukan kegagalan, tapi hasil kosong yang sah.
    if any(keyword in error_str for keyword in ("no results", "no result found", "no valid results")):
        return EmptyResultsError(f"Empty results: {exception}")
    elif any(keyword in error_str for keyword in ("rate", "429", "too many requests")):
        return RateLimitError(f"Rate limit detected: {exception}")
    elif any(keyword in error_str for keyword in ("block", "forbidden", "403", "captcha", "access denied")):
        return BlockedError(f"Blocked: {exception}")
    elif proxy and any(keyword in error_str for keyword in ("proxy", "socks", "connection refused", "tunnel")):
        return ProxyError(f"Proxy failure ({redact_proxy_url(proxy)}): {exception}")
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
    fallback_chain: Optional[List[str]] = None,
    forced_proxy: Optional[str] = None,
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
        backend: Backend engine(s) – comma-separated, 'auto', or a name
            configured under `engines:` (serper/serpapi/brave) / `profiles:`.
        user_agent: Custom User-Agent string (None = auto-rotate).
        verify: SSL certificate verification (True/False or path to CA).
        fallback_backends: If True, try alternative backends on failure.
        fallback_chain: Explicit fallback order (e.g. ['google', 'serper']).
            When None, `search.fallback` from atdork.yml is used, falling
            back to FALLBACK_BACKENDS.
        forced_proxy: Paksa proxy ini untuk percobaan pertama (dipakai oleh
            FallbackManager untuk menerapkan keputusan rotasi proxy).

    Returns:
        List of result dicts with keys 'title', 'href', 'body'.
        List kosong bila semua backend tidak punya hasil (query sah tanpa hasil).

    Raises:
        SearchError: When all backends and retries are exhausted.
    """
    # ── User-Agent ─────────────────────────────────────────────────────
    if user_agent is None:
        user_agent = get_random_user_agent()
        logger.debug("Using random UA: %s...", user_agent[:60])

    # ── Build Backend Queue ────────────────────────────────────────────
    # Chain/profiles come from atdork.yml (search.fallback / profiles) unless
    # an explicit fallback_chain was passed by the caller.
    if fallback_chain is None:
        fallback_chain = _config_section("search").get("fallback")
    chain = _normalize_chain(fallback_chain)
    profiles = _config_section("profiles")
    backends_to_try = resolve_backend_queue(
        backend, fallback_backends, chain, profiles or None
    )

    last_error: Optional[SearchError] = None
    config_error: Optional[SearchError] = None
    current_proxy: Optional[str] = None

    # ── Iterate Backends ───────────────────────────────────────────────
    for backend_name in backends_to_try:
        logger.info("Trying backend: %s", backend_name)

        # API provider configured under `engines:` in atdork.yml?
        try:
            provider = get_provider(backend_name)
        except ProviderError as pe:
            # Unusable engine (missing key, bad type) — config won't fix
            # itself mid-run: log clearly and let the fallback continue.
            last_error = ProviderConfigError(str(pe))
            config_error = last_error
            logger.warning("Backend %s unusable: %s", backend_name, pe)
            break
        if provider is not None:
            logger.debug("Backend %s resolves to API provider %s",
                         backend_name, type(provider).__name__)

        for attempt in range(retries + 1):
            # ── Proxy Selection ──────────────────────────────────────────
            if attempt == 0 and forced_proxy:
                # Proxy yang dipaksakan (keputusan rotasi dari FallbackManager)
                current_proxy = forced_proxy
            elif proxy_manager:
                try:
                    current_proxy = proxy_manager.get_proxy()
                    if current_proxy is None and getattr(proxy_manager, '_strict', False):
                        raise ProxyError("No proxy available in strict mode")
                except RuntimeError as exc:
                    raise ProxyError(str(exc)) from exc
            else:
                # Tanpa proxy_manager: paksa terus proxy yang sama di retry,
                # jangan diam-diam jatuh ke koneksi langsung.
                current_proxy = forced_proxy

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
                if provider is not None:
                    # Third-party API (serper / serpapi / brave, ...)
                    start_time = time.time()
                    results = provider.search(
                        query,
                        max_results=max_results,
                        region=region,
                        safesearch=safesearch,
                        timelimit=timelimit,
                        timeout=current_timeout,
                        proxy=current_proxy,
                        verify=verify,
                        user_agent=user_agent,
                    )
                    elapsed = time.time() - start_time
                    logger.debug(
                        "Provider %s returned %d results in %.2fs",
                        backend_name, len(results), elapsed
                    )
                else:
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

            except ProviderError as pe:
                # API provider failure → translate to the SearchError
                # hierarchy and decide: next backend or retry.
                search_error = _translate_provider_error(pe)
                last_error = search_error
                if isinstance(search_error, ProviderConfigError):
                    config_error = search_error
                logger.warning(
                    "Provider %s failed [kind=%s]: %s",
                    backend_name, pe.kind, search_error
                )

                if pe.kind == "network" and proxy_manager and current_proxy:
                    proxy_manager.report_failure(current_proxy)

                if isinstance(search_error, (RateLimitError, BlockedError, ProviderConfigError)):
                    # quota / rate limit / auth / bad config → don't retry
                    # this provider, let the fallback chain continue.
                    break

                # Network/parse/api errors → rotate UA and retry this backend
                user_agent = get_random_user_agent()
                continue

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
                    attempt + 1, retries + 1, backend_name, redact_proxy_url(current_proxy), search_error
                )

                # Report failure to proxy manager
                if proxy_manager and current_proxy:
                    proxy_manager.report_failure(current_proxy)

                # Query tanpa hasil → bukan error, langsung ke backend berikutnya
                if isinstance(search_error, EmptyResultsError):
                    logger.info(
                        "Backend %s has no results for this query, trying the next backend.",
                        backend_name,
                    )
                    break

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
    # Konfigurasi provider rusak (api_key hilang, dll) bukan "query tanpa
    # hasil" — naikkan error-nya agar pengguna tahu persis apa yang salah.
    if config_error is not None:
        raise config_error

    # Semua backend balik tanpa hasil (bukan error jaringan) → hasil kosong
    # yang sah. Ini penting agar query tanpa hasil tidak ditandai "failed"
    # dan terus-menerus diulang oleh --resume.
    if isinstance(last_error, EmptyResultsError):
        logger.info("No results for query '%s' on any backend.", query[:50])
        return []

    raise SearchError(
        f"Failed to fetch results for query '{query[:50]}...' "
        f"after trying {len(backends_to_try)} backend(s) "
        f"with {retries + 1} attempt(s) each. "
        f"Last error: {last_error}"
    )
