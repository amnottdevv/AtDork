"""
Atdork – Serper.dev provider (https://serper.dev)

Google results via a REST API:
    POST https://google.serper.dev/search
    Header: X-API-KEY: <key>
    Body:   {"q": "...", "num": 20, "gl": "us", "hl": "en"}

Response: {"organic": [{"position", "title", "link", "snippet"}, ...]}

Notes:
    - `region` maps to gl/hl; `safesearch` and `timelimit` are not supported
      by the Serper API and are ignored (see docs/engines.md).
"""

from typing import Any, Dict, List, Optional

from core.providers.base import BaseProvider, ProviderError, split_region
from lib.redactor import redact_secrets


class SerperProvider(BaseProvider):
    name = "serper"
    api_key_env = "SERPER_API_KEY"
    MAX_RESULTS_CAP = 100
    ENDPOINT = "https://google.serper.dev/search"

    def _map_error(self, response) -> ProviderError:
        status = response.status_code
        body = redact_secrets((response.text or "")[:300])
        lower = body.lower()

        if status in (401, 403):
            # Serper uses 401/403 for both bad keys and exhausted credits —
            # the response body disambiguates.
            if "credit" in lower or "quota" in lower or "balance" in lower:
                kind = "quota"
            elif "key" in lower or "invalid" in lower or "unauthorized" in lower:
                kind = "auth"
            else:
                kind = "auth" if status == 401 else "quota"
        elif status == 402:
            kind = "quota"
        elif status == 429:
            kind = "rate_limit"
        elif status >= 500:
            kind = "network"
        else:
            kind = "api"
        return ProviderError(kind, f"serper: HTTP {status}: {body}")

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
        gl, hl = split_region(region)
        payload: Dict[str, Any] = {
            "q": query,
            "num": min(max_results, self.MAX_RESULTS_CAP),
            "gl": gl,
            "hl": hl,
        }
        # Provider-specific overrides from engines.serper in atdork.yml
        for opt in ("location", "autocorrect", "page"):
            if opt in self.options:
                payload[opt] = self.options[opt]

        data = self._request(
            "POST",
            self.ENDPOINT,
            json_body=payload,
            headers={
                "X-API-KEY": self.api_key,
                "Content-Type": "application/json",
            },
            timeout=timeout,
            proxy=proxy,
            verify=verify,
            user_agent=user_agent,
        )
        if not isinstance(data, dict):
            raise ProviderError("parse", "serper: unexpected response shape")

        organic = data.get("organic") or []
        return [
            {
                "title": item.get("title") or "",
                "href": item.get("link") or "",
                "body": item.get("snippet") or "",
            }
            for item in organic
            if isinstance(item, dict) and item.get("link")
        ]
