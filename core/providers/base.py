"""
Atdork – Base class for third-party search API providers.

A provider wraps a paid/free search API (Serper.dev, SerpApi, Brave Search
API, ...) and normalises its responses to AtDork's internal result shape:

    {"title": str, "href": str, "body": str}

so every downstream stage (validation, filtering, cache, output formats,
resume) works unchanged.

Errors are reported as ProviderError with a machine-readable `kind`:

    quota       – credits/queries exhausted → scanner falls back to the next backend
    rate_limit  – HTTP 429 / throttled     → same treatment as scraping rate limits
    auth        – invalid key              → skip backend, clear message
    config      – engine not configured    → skip backend, clear message
    blocked     – access denied            → skip backend
    network     – timeouts / connection    → retried like scraping errors
    parse       – malformed response       → retried like scraping errors
    api         – other API errors         → retried like scraping errors

All messages passed through redact_secrets() so API keys never reach logs.
"""

import threading
import time
from typing import Any, Dict, List, Mapping, Optional, Tuple

import requests

from lib.redactor import mask_secret, redact_secrets


class ProviderError(Exception):
    """Provider failure with a machine-readable `kind` (see module docstring)."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


def split_region(region: Optional[str]) -> Tuple[str, str]:
    """'us-en' → ('us', 'en'); anything malformed → ('us', 'en')."""
    if isinstance(region, str) and "-" in region:
        gl, _, hl = region.partition("-")
        gl, hl = gl.strip().lower(), hl.strip().lower()
        if gl and hl:
            return gl, hl
    return "us", "en"


class BaseProvider:
    """Shared HTTP plumbing, rate limiting (qps) and normalisation."""

    #: registry id, must match the key used under `engines:` in atdork.yml
    name: str = "base"
    #: environment variable recommended in error messages
    api_key_env: str = "API_KEY"
    #: hard cap per request (provider-specific; see docs/engines.md)
    MAX_RESULTS_CAP: int = 100

    def __init__(self, api_key: Optional[str] = None, *, qps: float = 1.0,
                 timeout: int = 10, **options: Any):
        self.api_key = api_key or ""
        try:
            self.qps = float(qps)
        except (TypeError, ValueError):
            self.qps = 1.0
        try:
            self.timeout = int(timeout)
        except (TypeError, ValueError):
            self.timeout = 10
        self.options = options
        self._local = threading.local()   # per-thread requests.Session
        self._lock = threading.Lock()     # protects the throttle timestamp
        self._next_slot = 0.0

    def __repr__(self) -> str:
        return f"<{type(self).__name__} key={mask_secret(self.api_key)}>"

    # ── Session / throttling ───────────────────────────────────────────────
    @property
    def session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            self._local.session = session
        return session

    def ensure_configured(self) -> None:
        if not self.api_key:
            raise ProviderError(
                "config",
                f"engines.{self.name}.api_key is not set — export "
                f"{self.api_key_env} or set api_key under engines.{self.name} "
                "in atdork.yml",
            )

    def _throttle(self) -> None:
        """Local rate limit: at most `qps` requests per second (0 = unlimited)."""
        if self.qps <= 0:
            return
        interval = max(1.0 / self.qps, 0.05)
        with self._lock:
            now = time.monotonic()
            wait = self._next_slot - now
            self._next_slot = max(now, self._next_slot) + interval
        if wait > 0:
            time.sleep(wait)

    # ── HTTP ───────────────────────────────────────────────────────────────
    def _map_error(self, response: "requests.Response") -> ProviderError:
        """Map an HTTP error response to a ProviderError (override per engine)."""
        status = response.status_code
        body = redact_secrets((response.text or "")[:300])
        if status in (401, 403):
            kind = "auth"
        elif status == 402:
            kind = "quota"
        elif status == 429:
            kind = "rate_limit"
        elif status >= 500:
            kind = "network"
        else:
            kind = "api"
        return ProviderError(kind, f"{self.name}: HTTP {status}: {body}")

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
        timeout: Optional[int] = None,
        proxy: Optional[str] = None,
        verify: Any = True,
        user_agent: Optional[str] = None,
    ) -> Any:
        """Perform a throttled request; return the parsed JSON body.

        Raises ProviderError with the right `kind` for any failure.
        """
        self.ensure_configured()
        self._throttle()

        request_headers: Dict[str, str] = dict(headers or {})
        if user_agent:
            request_headers["User-Agent"] = user_agent

        kwargs: Dict[str, Any] = {
            "params": dict(params) if params else None,
            "headers": request_headers,
            "timeout": timeout or self.timeout,
            "verify": verify,
        }
        if json_body is not None:
            kwargs["json"] = json_body
        if proxy:
            kwargs["proxies"] = {"http": proxy, "https": proxy}

        try:
            response = self.session.request(method, url, **kwargs)
        except requests.exceptions.RequestException as exc:
            raise ProviderError(
                "network",
                f"{self.name}: request failed ({type(exc).__name__}): "
                f"{redact_secrets(str(exc))}",
            ) from None

        if response.status_code >= 400:
            raise self._map_error(response)

        try:
            return response.json()
        except ValueError:
            body = redact_secrets((response.text or "")[:300])
            raise ProviderError(
                "parse",
                f"{self.name}: response is not valid JSON: {body}",
            ) from None

    # ── Search ─────────────────────────────────────────────────────────────
    def _fetch(
        self,
        query: str,
        max_results: int,
        region: str,
        safesearch: str,
        timelimit: Optional[str],
        timeout: int,
        proxy: Optional[str],
        verify: Any,
        user_agent: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Engine-specific request + normalisation (override per engine)."""
        raise NotImplementedError

    def search(
        self,
        query: str,
        *,
        max_results: int = 20,
        region: str = "us-en",
        safesearch: str = "moderate",
        timelimit: Optional[str] = None,
        timeout: Optional[int] = None,
        proxy: Optional[str] = None,
        verify: Any = True,
        user_agent: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Run one query and return normalised {title, href, body} results."""
        try:
            cap = int(max_results)
        except (TypeError, ValueError):
            cap = 20
        cap = max(cap, 1)
        requested = min(cap, self.MAX_RESULTS_CAP)

        raw = self._fetch(
            query, requested, region, safesearch, timelimit,
            timeout or self.timeout, proxy, verify, user_agent,
        )
        results: List[Dict[str, Any]] = []
        for item in raw or []:
            if not isinstance(item, dict):
                continue
            href = item.get("href")
            if not href:
                continue
            results.append({
                "title": item.get("title") or href,
                "href": href,
                "body": item.get("body") or "",
            })
            if len(results) >= cap:
                break
        return results
