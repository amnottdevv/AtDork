"""
AtDork – Proxy URL Redactor (lib/redactor.py)
Menghapus kredensial dari URL proxy sebelum logging/display.
"""

from urllib.parse import urlparse, urlunparse

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
