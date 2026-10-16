"""
AtDork – Proxy URL Redactor (lib/redactor.py)
Menghapus kredensial dari URL proxy sebelum logging/display.
"""

import re
from typing import Optional
from urllib.parse import urlparse, urlunparse

# Query-string secrets: api_key, token, subscription-token, key, ...
_SECRET_QS_RE = re.compile(
    r"(?i)([?&](?:api_?key|api-key|token|access_?token|subscription[-_]token"
    r"|key|secret|password|auth|q)=" r")[^&\s'\"]+"
)
# Also redact the value after '=' when the *name* itself is a bare secret key
# (e.g. 'api_key=abc' inside exception messages from requests).
_BEARER_RE = re.compile(r"(?i)(bearer\s+)[a-z0-9._\-]+")
_USERINFO_RE = re.compile(r"(://)[^/\s:@]+:[^/\s@]+@")


def redact_secrets(text: Optional[str]) -> Optional[str]:
    """
    Scrub API keys, tokens and URL credentials from arbitrary text
    (log lines, exception messages, HTTP error bodies).

    Example:
        'GET https://serpapi.com/search?api_key=SECRET123&q=x'
        → 'GET https://serpapi.com/search?api_key=***&q=x'
    """
    if not text or not isinstance(text, str):
        return text
    text = _SECRET_QS_RE.sub(r"\1***", text)
    text = _BEARER_RE.sub(r"\1***", text)
    text = _USERINFO_RE.sub(r"\1***:***@", text)
    return text


def mask_secret(value: Optional[str]) -> str:
    """Short masked form of a secret for repr/log: '***cd34' or '(not set)'."""
    if not value:
        return "(not set)"
    if len(value) <= 4:
        return "****"
    return f"***{value[-4:]}"


def redact_proxy_url(proxy_url: str) -> str:
    """
    Ganti username:password di URL proxy dengan '***'.
    Contoh: http://user:pass@host:8080 → http://***:***@host:8080
    """
    if not proxy_url:
        return "None"
    try:
        parsed = urlparse(proxy_url)
        if parsed.username or parsed.password:
            # change userpass to ==***
            host_with_port = parsed.hostname
            if parsed.port:
                host_with_port += f":{parsed.port}"
            redacted = f"{parsed.scheme}://***:***@{host_with_port}"
            if parsed.path:
                redacted += parsed.path
            if parsed.query:
                redacted += f"?{parsed.query}"
            if parsed.fragment:
                redacted += f"#{parsed.fragment}"
            return redacted
        return proxy_url
    except Exception:
        return "[invalid proxy]"
