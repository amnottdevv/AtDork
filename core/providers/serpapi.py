"""
Atdork – SerpApi provider (https://serpapi.com)

Multi-engine SERP API:
    GET https://serpapi.com/search
        ?engine=google&q=...&api_key=...&num=20&gl=us&hl=en&tbs=qdr:d

Response (engine=google): {"organic_results": [{"position","title","link",
"snippet"}, ...]}

Notes:
    - `region` maps to gl/hl; `timelimit` maps to tbs=qdr:d|w|m|y.
    - `safesearch` is engine-dependent and not forwarded (docs/engines.md).
    - SerpApi reports many failures as HTTP 200 with an `error` field; those
      are mapped by inspecting the message (credits / API key / throttling).
"""

from typing import Any, Dict, List, Optional

from core.providers.base import BaseProvider, ProviderError, split_region
from lib.redactor import redact_secrets

_TBS_MAP = {"d": "qdr:d", "w": "qdr:w", "m": "qdr:m", "y": "qdr:y"}


class SerpApiProvider(BaseProvider):
    name = "serpapi"
    api_key_env = "SERPAPI_KEY"
    MAX_RESULTS_CAP = 100
    ENDPOINT = "https://serpapi.com/search"

    def _map_error(self, response) -> ProviderError:
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
        return ProviderError(kind, f"serpapi: HTTP {status}: {body}")

    @staticmethod
    def _classify_error_field(message: str) -> str:
        lower = (message or "").lower()
        if "credit" in lower or "quota" in lower or "plan" in lower or "balance" in lower:
            return "quota"
        if "api key" in lower or "invalid" in lower or "unauthorized" in lower:
            return "auth"
        if "too many" in lower or "rate" in lower or "slow" in lower:
            return "rate_limit"
        return "api"

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
        params: Dict[str, Any] = {
            "engine": self.options.get("engine", "google"),
            "q": query,
            "api_key": self.api_key,
            "num": min(max_results, self.MAX_RESULTS_CAP),
            "gl": gl,
            "hl": hl,
        }
        if timelimit in _TBS_MAP:
            params["tbs"] = _TBS_MAP[timelimit]
        for opt in ("location", "safe", "tbm"):
            if opt in self.options:
                params[opt] = self.options[opt]

        data = self._request(
            "GET",
            self.ENDPOINT,
            params=params,
            timeout=timeout,
            proxy=proxy,
            verify=verify,
            user_agent=user_agent,
        )
        if not isinstance(data, dict):
            raise ProviderError("parse", "serpapi: unexpected response shape")

        # SerpApi reports many failures as HTTP 200 + {"error": "..."}.
        if data.get("error"):
            message = redact_secrets(str(data["error"])[:300])
            raise ProviderError(
                self._classify_error_field(message),
                f"serpapi: {message}",
            )

        results = data.get("organic_results") or []
        return [
            {
                "title": item.get("title") or "",
                "href": item.get("link") or "",
                "body": item.get("snippet") or "",
            }
            for item in results
            if isinstance(item, dict) and item.get("link")
        ]
