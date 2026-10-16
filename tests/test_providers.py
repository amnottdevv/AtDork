"""
Unit tests for the third-party API providers (core/providers/) and their
integration with core.scanner's backend fallback chain.

No real network: _request / DDGS are mocked everywhere.
"""

import pytest
from unittest.mock import patch

from core.providers import (
    PROVIDER_CLASSES,
    ProviderError,
    get_provider,
    register,
    reset_registry,
)
from core.providers.base import BaseProvider, split_region
from core.providers.brave import BraveApiProvider
from core.providers.serper import SerperProvider
from core.providers.serpapi import SerpApiProvider
from core.scanner import (
    ProviderConfigError,
    QuotaExceededError,
    resolve_backend_queue,
    search_dork,
)
from lib.redactor import mask_secret, redact_secrets


@pytest.fixture(autouse=True)
def clean_registry():
    reset_registry()
    yield
    reset_registry()


class FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


# ── Helpers ────────────────────────────────────────────────────────────────

def test_split_region():
    assert split_region("us-en") == ("us", "en")
    assert split_region("id-id") == ("id", "id")
    assert split_region("bogus") == ("us", "en")
    assert split_region(None) == ("us", "en")
    assert split_region("-en") == ("us", "en")


def test_redact_secrets():
    text = "GET https://serpapi.com/search?api_key=SECRET123&q=x failed"
    assert "SECRET123" not in redact_secrets(text)
    assert "api_key=***" in redact_secrets(text)
    assert "SECRET123" not in redact_secrets("https://user:SECRET123@host:8080")
    assert mask_secret("abcd1234cd34") == "***cd34"
    assert mask_secret("") == "(not set)"


# ── Normalisation (mocked _request) ────────────────────────────────────────

def test_serper_normalisation(monkeypatch):
    provider = SerperProvider("key")
    monkeypatch.setattr(
        provider, "_request",
        lambda *a, **k: {"organic": [
            {"position": 1, "title": "T1", "link": "https://a.test/", "snippet": "S1"},
            {"position": 2, "title": "T2", "link": "https://b.test/", "snippet": "S2"},
            {"position": 3, "title": "No link", "snippet": "skip"},
        ]},
    )
    results = provider.search("q", max_results=10)
    assert results == [
        {"title": "T1", "href": "https://a.test/", "body": "S1"},
        {"title": "T2", "href": "https://b.test/", "body": "S2"},
    ]


def test_serpapi_normalisation_and_tbs(monkeypatch):
    provider = SerpApiProvider("key")
    captured = {}

    def fake_request(method, url, **kwargs):
        captured.update(kwargs.get("params") or {})
        return {"organic_results": [
            {"position": 1, "title": "T", "link": "https://c.test/", "snippet": "S"},
        ]}

    monkeypatch.setattr(provider, "_request", fake_request)
    results = provider.search("q", max_results=5, region="id-id", timelimit="d")
    assert results == [{"title": "T", "href": "https://c.test/", "body": "S"}]
    assert captured["gl"] == "id" and captured["hl"] == "id"
    assert captured["tbs"] == "qdr:d"
    assert captured["api_key"] == "key"


def test_brave_normalisation_params_and_cap(monkeypatch):
    provider = BraveApiProvider("key")
    captured = {}

    def fake_request(method, url, **kwargs):
        captured.update(kwargs.get("params") or {})
        captured["headers"] = kwargs.get("headers")
        return {"web": {"results": [
            {"title": "T", "url": "https://d.test/", "description": "S"},
            {"title": "T2", "url": "https://e.test/", "description": "S2"},
        ]}}

    monkeypatch.setattr(provider, "_request", fake_request)
    results = provider.search("q", max_results=50, safesearch="on", timelimit="w")
    assert len(results) == 2
    assert results[0]["href"] == "https://d.test/"
    assert captured["count"] == 20          # MAX_RESULTS_CAP
    assert captured["safesearch"] == "strict"
    assert captured["freshness"] == "pw"
    assert captured["headers"]["X-Subscription-Token"] == "key"


def test_result_sliced_to_max_results(monkeypatch):
    provider = SerperProvider("key")
    monkeypatch.setattr(
        provider, "_request",
        lambda *a, **k: {"organic": [
            {"title": f"T{i}", "link": f"https://x.test/{i}", "snippet": ""}
            for i in range(30)
        ]},
    )
    assert len(provider.search("q", max_results=7)) == 7


# ── Error mapping ──────────────────────────────────────────────────────────

def test_http_429_maps_to_rate_limit():
    provider = SerperProvider("key")
    err = provider._map_error(FakeResponse(429, text="slow down"))
    assert err.kind == "rate_limit"


def test_serper_403_body_disambiguation():
    provider = SerperProvider("key")
    quota = provider._map_error(FakeResponse(403, text="Insufficient credits"))
    assert quota.kind == "quota"
    auth = provider._map_error(FakeResponse(403, text="Invalid api key"))
    assert auth.kind == "auth"
    # no body hints: 403 → quota, 401 → auth (serper semantics)
    assert provider._map_error(FakeResponse(403, text="")).kind == "quota"
    assert provider._map_error(FakeResponse(401, text="")).kind == "auth"


def test_serpapi_error_field_classification(monkeypatch):
    provider = SerpApiProvider("key")
    monkeypatch.setattr(
        provider, "_request",
        lambda *a, **k: {"error": "Your account ran out of credits."},
    )
    with pytest.raises(ProviderError) as exc:
        provider.search("q")
    assert exc.value.kind == "quota"

    monkeypatch.setattr(
        provider, "_request",
        lambda *a, **k: {"error": "Invalid API key."},
    )
    with pytest.raises(ProviderError) as exc:
        provider.search("q")
    assert exc.value.kind == "auth"


def test_network_error_wrapped_and_redacted(monkeypatch):
    import requests

    provider = SerpApiProvider("key")

    def boom(*a, **k):
        raise requests.exceptions.ConnectionError(
            "failed https://serpapi.com/search?api_key=TOPSECRET"
        )

    monkeypatch.setattr(provider.session, "request", boom)
    with pytest.raises(ProviderError) as exc:
        provider.search("q")
    assert exc.value.kind == "network"
    assert "TOPSECRET" not in str(exc.value)


def test_missing_api_key_message():
    provider = SerperProvider("")
    with pytest.raises(ProviderError) as exc:
        provider.search("q")
    assert exc.value.kind == "config"
    assert "engines.serper.api_key is not set" in str(exc.value)
    assert "SERPER_API_KEY" in str(exc.value)


def test_repr_masks_key():
    assert "secret-key-9876" not in repr(SerperProvider("secret-key-9876"))


# ── Registry ───────────────────────────────────────────────────────────────

def test_get_provider_unknown_returns_none():
    assert get_provider("definitely-not-configured") is None


def test_register_and_reset():
    fake = SerperProvider("k")
    register("serper", fake)
    assert get_provider("serper") is fake
    reset_registry()
    assert get_provider("serper") is None   # not in config either


def test_provider_classes_cover_supported_names():
    assert set(PROVIDER_CLASSES) == {"serper", "serpapi", "brave"}


def test_config_built_provider(monkeypatch):
    from core.config import _CURRENT
    _CURRENT.clear()
    _CURRENT.update({
        "engines": {"serper": {"type": "api", "api_key": "ck", "qps": 5}},
    })
    provider = get_provider("serper")
    assert isinstance(provider, SerperProvider)
    assert provider.api_key == "ck"
    assert provider.qps == 5
    # cached: same instance on second lookup
    assert get_provider("serper") is provider


def test_configured_engine_overrides_same_name_backend():
    """engines.brave (type: api) makes 'brave' resolve to the API provider."""
    from core.config import _CURRENT
    _CURRENT.clear()
    _CURRENT.update({"engines": {"brave": {"type": "api", "api_key": "bk"}}})
    provider = get_provider("brave")
    assert isinstance(provider, BraveApiProvider)


# ── Backend queue resolution ───────────────────────────────────────────────

def test_queue_auto_without_chain():
    assert resolve_backend_queue("auto", True) == ["auto"]
    assert resolve_backend_queue("auto", False) == ["auto"]


def test_queue_auto_with_chain_appends():
    assert resolve_backend_queue("auto", True, ["serper", "brave"]) == [
        "auto", "serper", "brave",
    ]


def test_queue_comma_list_honoured():
    assert resolve_backend_queue("google,bing", True) == ["google", "bing"]


def test_queue_single_plus_chain():
    assert resolve_backend_queue("google", True, ["serper"]) == ["google", "serper"]


def test_queue_no_fallback_returns_single():
    assert resolve_backend_queue("google", False) == ["google"]


def test_queue_profile_expansion():
    profiles = {"resilient": ["google", "serper", "google"]}
    # explicit profile = explicit chain, even with fallback disabled
    assert resolve_backend_queue("resilient", False, None, profiles) == [
        "google", "serper",
    ]


# ── scanner integration ────────────────────────────────────────────────────

class QuotaProvider(BaseProvider):
    name = "qprov"
    calls = 0

    def _fetch(self, *args, **kwargs):
        QuotaProvider.calls += 1
        raise ProviderError("quota", "qprov: out of credits")


class OkProvider(BaseProvider):
    name = "oprov"

    def _fetch(self, *args, **kwargs):
        return [{"title": "T", "href": "https://ok.test/1", "body": "b"}]


def test_quota_error_falls_back_without_retry():
    QuotaProvider.calls = 0
    register("qprov", QuotaProvider("k"))
    register("oprov", OkProvider("k"))

    results = search_dork(
        "test query", backend="qprov,oprov", retries=3, fallback_backends=True,
    )
    assert results and results[0]["href"] == "https://ok.test/1"
    # quota must not be retried on the same provider
    assert QuotaProvider.calls == 1


def test_unconfigured_engine_raises_clear_error(monkeypatch):
    from core.config import _CURRENT
    _CURRENT.clear()
    _CURRENT.update({"engines": {"serper": {"type": "api", "api_key": ""}}})

    class EmptyDDGS:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def text(self, *a, **k):
            return []

    import core.scanner as scanner
    monkeypatch.setattr(scanner, "DDGS", EmptyDDGS)

    with pytest.raises(ProviderConfigError, match="engines.serper.api_key is not set"):
        search_dork("q", backend="serper", retries=1, fallback_backends=False)
    _CURRENT.clear()


def test_fallback_results_returned_despite_broken_engine(monkeypatch):
    """A broken engine is skipped with a warning; fallback results win."""
    from core.config import _CURRENT
    _CURRENT.clear()
    _CURRENT.update({"engines": {"serper": {"type": "api", "api_key": ""}}})

    class HitDDGS:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def text(self, *a, **k):
            return [{"title": "g", "href": "https://hit.test", "body": "x", "date": None}]

    import core.scanner as scanner
    monkeypatch.setattr(scanner, "DDGS", HitDDGS)

    results = search_dork("q", backend="serper", retries=1, verify=False)
    assert results and results[0]["href"] == "https://hit.test"
    _CURRENT.clear()


def test_quota_error_is_rate_limit_for_classifier():
    from core.case.error_classifier import ErrorCategory, classify_error
    err = QuotaExceededError("API quota exceeded (rate limit): x")
    assert classify_error(err) == ErrorCategory.RATE_LIMIT
    assert isinstance(err, Exception)
