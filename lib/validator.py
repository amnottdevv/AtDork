"""
Atdork – Output Validator (Robust, Granular, Backward‑Compatible)

Memvalidasi dan membersihkan hasil pencarian (URL, title, body) dengan kontrol penuh.
Semua fungsi publik memiliki fallback: jika parameter tidak valid, mereka
mengembalikan False / list kosong / statistik nol, *bukan* raise exception.
"""

import re
import logging
from urllib.parse import urlparse
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# ── Spam patterns ──────────────────────────────────────────────────────
SPAM_PATTERNS = [
    r"(?i)\b(buy now|click here|free money|act now|limited offer|best price|discount|cheap)\b",
    r"(?i)\b(porn|xxx|adult|sex|casino|gambling|slot|poker|bet|lottery)\b",
    r"(?i)\b(SEO|marketing|traffic|visitors|backlink|earn money|work from home)\b",
    r"(?i)(\.xyz|\.top|\.loan|\.win|\.stream|\.download)\b",
]

ALLOWED_SCHEMES = frozenset({"http", "https", "ftp"})
VALID_URL_MODES  = frozenset({"only", "path", "params", "all", "false"})

# Default constants (used when strict=True)
DEFAULT_MIN_TITLE = 5
DEFAULT_MIN_BODY  = 10


# ── URL Validation ─────────────────────────────────────────────────────
def is_valid_url(url: Any, mode: str = "all") -> bool:
    """
    Validate a URL string according to *mode*.

    mode:
        "only"   – scheme + host + TLD required; path & params ignored
        "path"   – if path present, it must be well‑formed
        "params" – if query present, it must contain '='
        "all"    – full validation (default)
        "false"  – skip URL validation (always True)

    Returns False for any invalid input (None, non‑string, missing parts).
    """
    # ── guard clauses ──────────────────────────────────────────────
    if mode not in VALID_URL_MODES:
        logger.warning("is_valid_url: unknown mode '%s' – falling back to 'all'", mode)
        mode = "all"

    if mode == "false":
        return True

    if not isinstance(url, str) or not url:
        return False

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    # Scheme must be allowed
    if parsed.scheme not in ALLOWED_SCHEMES:
        return False

    # Host must exist and contain a dot (real FQDN / IPv4 not supported here)
    if not parsed.netloc or "." not in parsed.netloc:
        return False

    # Mode‑specific checks
    if mode == "only":
        return True

    if mode == "path":
        # Path, if present, must start with '/'
        if parsed.path and not parsed.path.startswith("/"):
            return False
        return True

    if mode == "params":
        # Query, if present, must contain '='
        if parsed.query and "=" not in parsed.query:
            return False
        return True

    # mode == "all"  → already checked scheme + host, nothing more to enforce
    return True


# ── Spam Detection ──────────────────────────────────────────────────────
def is_spam_text(text: Any) -> bool:
    """Return True if *text* contains known spam patterns.  Graceful on None."""
    if not text:
        return False
    if not isinstance(text, str):
        return False
    for pattern in SPAM_PATTERNS:
        try:
            if re.search(pattern, text):
                return True
        except re.error:
            continue          # ignore malformed patterns (should never happen)
    return False


# ── Single Result Validation ────────────────────────────────────────────
def is_valid_result(
    result: Any,
    min_title: Optional[int] = None,
    min_desc: Optional[int] = None,
    check_spam: bool = True,
    url_mode: str = "all",
) -> bool:
    """
    Validate one search result dict.

    Returns True only if all configured checks pass.
    Gracefully handles None / missing keys / weird types.
    """
    # ── input guard ────────────────────────────────────────────────
    if not isinstance(result, dict):
        return False

    url   = result.get("href", "")
    title = result.get("title", "")
    body  = result.get("body", "")

    # Normalise to strings
    url   = url.strip()   if isinstance(url, str)   else ""
    title = title.strip() if isinstance(title, str) else ""
    body  = body.strip()  if isinstance(body, str)  else ""

    # 1. URL
    if not is_valid_url(url, mode=url_mode):
        return False

    # 2. Title length
    if min_title is not None:
        if not title or len(title) < min_title:
            return False

    # 3. Body / description length
    if min_desc is not None:
        if not body or len(body) < min_desc:
            return False

    # 4. Spam
    if check_spam:
        if is_spam_text(title) or is_spam_text(body):
            return False

    return True


# ── Batch Filtering ────────────────────────────────────────────────────
def filter_results(
    results: Any,
    strict: Optional[bool] = None,      # backward‑compatible shortcut
    min_title: Optional[int] = None,
    min_desc: Optional[int] = None,
    check_spam: bool = True,
    url_mode: str = "all",
) -> List[Dict]:
    """
    Filter a list of result dicts.

    ``strict`` is a convenience switch:
        - strict=True   → enable tight defaults (title≥5, desc≥10, spam on, url all)
        - strict=False  → disable ALL filtering (same as old ``--no-validate``)

    When ``strict`` is None, the individual parameters are honoured.
    """
    # ── strict shortcut ────────────────────────────────────────────
    if strict is True:
        min_title = DEFAULT_MIN_TITLE
        min_desc  = DEFAULT_MIN_BODY
        check_spam = True
        url_mode   = "all"
    elif strict is False:
        min_title = None
        min_desc  = None
        check_spam = False
        url_mode   = "false"

    # ── input guard ────────────────────────────────────────────────
    if not isinstance(results, list):
        return []

    if not results:
        return []

    filtered = []
    for r in results:
        try:
            if is_valid_result(
                r,
                min_title=min_title,
                min_desc=min_desc,
                check_spam=check_spam,
                url_mode=url_mode,
            ):
                filtered.append(r)
        except Exception:
            # individual result should never crash the whole filter
            continue

    return filtered


# ── Statistics ──────────────────────────────────────────────────────────
def get_filter_stats(original: int, filtered: int) -> Dict[str, int]:
    """Return a small stats dict.  Negative values are clamped to 0."""
    orig = max(0, original)
    filt = max(0, filtered)
    return {
        "original": orig,
        "filtered": filt,
        "removed": orig - filt if orig >= filt else 0,
    }
