"""
Atdork – Brave Search API provider (https://api.search.brave.com)

Official (non-scraping) Brave Search API:
    GET https://api.search.brave.com/res/v1/web/search?q=...&count=20
    Header: X-Subscription-Token: <key>

Response: {"web": {"results": [{"title","url","description"}, ...]}}

Notes:
    - One of the few providers that supports `safesearch`
      (on/moderate/off → strict/moderate/off) and `timelimit`
      (d/w/m/y → freshness=pd/pw/pm/py) natively.
    - `region` maps to country/search_lang.
    - Free tier caps `count` at 20 per request (MAX_RESULTS_CAP).
"""

from typing import Any, Dict, List, Optional

from core.providers.base import BaseProvider, ProviderError, split_region
from lib.redactor import redact_secrets

_FRESHNESS_MAP = {"d": "pd", "w": "pw", "m": "pm", "y": "py"}
_SAFE_MAP = {"on": "strict", "moderate": "moderate", "off": "off"}


class BraveApiProvider(BaseProvider):
    name = "brave"
    api_key_env = "BRAVE_API_KEY"
    MAX_RESULTS_CAP = 20
    ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

    def _map_error(self, response) -> ProviderError:
        status = response.status_code
        body = redact_secrets((response.text or "")[:300])
        lower = body.lower()
        if status in (401, 403):
            kind = "auth"
        elif status == 402 or "quota" in lower or "credits" in lower:
            kind = "quota"
        elif status == 429:
            kind = "rate_limit"
        elif status >= 500:
            kind = "network"
        else:
            kind = "api"
        return ProviderError(kind, f"brave: HTTP {status}: {body}")

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
        country, search_lang = split_region(region)
        params: Dict[str, Any] = {
            "q": query,
            "count": min(max_results, self.MAX_RESULTS_CAP),
            "country": country,
            "search_lang": search_lang,
            "safesearch": _SAFE_MAP.get(safesearch, "moderate"),
        }
        if timelimit in _FRESHNESS_MAP:
            params["freshness"] = _FRESHNESS_MAP[timelimit]
        for opt in ("offset", "extra_snippets", "goggles_id"):
            if opt in self.options:
                params[opt] = self.options[opt]

        data = self._request(
            "GET",
            self.ENDPOINT,
            params=params,
            headers={
                "X-Subscription-Token": self.api_key,
                "Accept": "application/json",
            },
            timeout=timeout,
            proxy=proxy,
            verify=verify,
            user_agent=user_agent,
        )
        if not isinstance(data, dict):
            raise ProviderError("parse", "brave: unexpected response shape")

        web = data.get("web") or {}
        results = web.get("results") or []
        return [
            {
                "title": item.get("title") or "",
                "href": item.get("url") or "",
                "body": item.get("description") or "",
            }
            for item in results
            if isinstance(item, dict) and item.get("url")
        ]
