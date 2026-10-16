"""
Atdork – Third-party search API providers (core/providers/).

Registry of API-backed engines configured under `engines:` in atdork.yml:

    engines:
      serper:
        type: api
        api_key: ${SERPER_API_KEY}
        qps: 1

`core.scanner` looks every backend name up here first; names that resolve to
a provider are executed against the API, everything else goes through the
built-in ddgs (scraping) path unchanged.

A configured engine name *overrides* a scraping backend of the same name —
e.g. `engines.brave.type: api` makes `--backend brave` use the official
Brave Search API instead of ddgs' Brave scraping backend.
"""

from typing import Any, Dict, Optional

from core.providers.base import BaseProvider, ProviderError, split_region
from core.providers.brave import BraveApiProvider
from core.providers.serper import SerperProvider
from core.providers.serpapi import SerpApiProvider

__all__ = [
    "BaseProvider",
    "ProviderError",
    "BraveApiProvider",
    "SerperProvider",
    "SerpApiProvider",
    "PROVIDER_CLASSES",
    "get_provider",
    "register",
    "reset_registry",
    "configured_engines",
]

#: engine name / spec `provider:` value → implementation class
PROVIDER_CLASSES = {
    "serper": SerperProvider,
    "serpapi": SerpApiProvider,
    "brave": BraveApiProvider,
}

#: resolved instances (explicit registrations + config-built, cached)
_instances: Dict[str, BaseProvider] = {}


def reset_registry() -> None:
    """Drop all resolved instances (tests / config reloads)."""
    _instances.clear()


def register(name: str, provider: BaseProvider) -> None:
    """Register an instance explicitly (takes precedence over config)."""
    _instances[name] = provider


def configured_engines() -> Dict[str, Any]:
    """The `engines:` section of the last loaded config ({} when absent)."""
    from core.config import get_setting  # local import: avoids import cycles

    engines = get_setting("engines")
    return engines if isinstance(engines, dict) else {}


def _build(name: str, spec: Dict[str, Any]) -> BaseProvider:
    ptype = spec.get("type", "api")
    if ptype != "api":
        raise ProviderError(
            "config",
            f"engines.{name}.type {ptype!r} is not supported (supported: api)",
        )

    class_name = spec.get("provider", name)
    cls = PROVIDER_CLASSES.get(class_name)
    if cls is None:
        raise ProviderError(
            "config",
            f"engines.{name}: unknown provider {class_name!r} "
            f"(supported: {', '.join(sorted(PROVIDER_CLASSES))})",
        )

    api_key = spec.get("api_key")
    if api_key is not None and not isinstance(api_key, str):
        raise ProviderError("config", f"engines.{name}.api_key must be a string")

    reserved = {"type", "provider", "api_key", "qps", "timeout"}
    options = {k: v for k, v in spec.items() if k not in reserved}
    return cls(
        api_key,
        qps=spec.get("qps", 1.0),
        timeout=spec.get("timeout", 10),
        **options,
    )


def get_provider(name: str) -> Optional[BaseProvider]:
    """
    Resolve a backend name to a provider instance.

    Returns None when the name is not a configured API engine (the caller
    then falls back to the ddgs scraping path). Raises ProviderError for
    engines that are configured but unusable (bad type, missing key, ...).
    """
    if name in _instances:
        return _instances[name]

    spec = configured_engines().get(name)
    if not isinstance(spec, dict):
        return None

    provider = _build(name, spec)
    _instances[name] = provider
    return provider
