"""
Atdork - Output Validator
Memvalidasi dan membersihkan hasil pencarian (URL, title, body).
Membantu menghilangkan spam, dead links, dan konten tidak relevan.
"""

import re
from urllib.parse import urlparse

# ---------- Pola umum spam ----------
SPAM_PATTERNS = [
    r"(?i)\b(buy now|click here|free money|act now|limited offer|best price|discount|cheap)\b",
    r"(?i)\b(porn|xxx|adult|sex|casino|gambling|slot|poker|bet|lottery)\b",
    r"(?i)\b(SEO|marketing|traffic|visitors|backlink|earn money|work from home)\b",
    r"(?i)(\.xyz|\.top|\.loan|\.win|\.stream|\.download)\b",  # TLD sering spam
]

# Skema URL yang dianggap valid
ALLOWED_SCHEMES = {"http", "https", "ftp"}

# Panjang minimal konten agar dianggap valid
MIN_TITLE_LENGTH = 5
MIN_BODY_LENGTH = 10


def is_valid_url(url: str) -> bool:
    """
    Memeriksa apakah string adalah URL yang valid dan aman.

    Returns:
        True jika URL memiliki skema yang diizinkan dan format benar.
    """
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme in ALLOWED_SCHEMES
            and bool(parsed.netloc)
            and "." in parsed.netloc  # minimal domain valid
        )
    except Exception:
        return False


def is_spam_text(text: str) -> bool:
    """
    Mendeteksi apakah teks mengandung pola spam umum.

    Args:
        text: string judul atau deskripsi

    Returns:
        True jika terdeteksi spam.
    """
    if not text:
        return False
    for pattern in SPAM_PATTERNS:
        if re.search(pattern, text):
            return True
    return False


def is_valid_result(result: dict, strict: bool = False) -> bool:
    """
    Memvalidasi satu hasil pencarian.

    Args:
        result: dictionary dengan keys 'title', 'href', 'body'
        strict: jika True, tolak hasil yang tidak memiliki snippet atau judul pendek

    Returns:
        True jika hasil lolos filter.
    """
    url = result.get("href", "").strip()
    title = result.get("title", "").strip()
    body = result.get("body", "").strip()

    # 1. URL harus valid
    if not is_valid_url(url):
        return False

    # 2. Judul tidak boleh spam dan cukup panjang
    if not title or len(title) < MIN_TITLE_LENGTH:
        return False
    if is_spam_text(title):
        return False

    # 3. Body tidak spam
    if is_spam_text(body):
        return False

    # 4. Jika strict, body harus ada dan cukup panjang
    if strict:
        if not body or len(body) < MIN_BODY_LENGTH:
            return False

    return True


def filter_results(results: list, strict: bool = False) -> list:
    """
    Menyaring daftar hasil pencarian, membuang yang tidak valid.

    Args:
        results: list dictionary hasil dari search_dork()
        strict: filter lebih ketat (body wajib ada)

    Returns:
        List hasil yang sudah difilter.
    """
    if not results:
        return []
    return [r for r in results if is_valid_result(r, strict=strict)]


def get_filter_stats(original: int, filtered: int) -> dict:
    """Hitung statistik filter untuk logging."""
    return {
        "original": original,
        "filtered": filtered,
        "removed": original - filtered,
    }
