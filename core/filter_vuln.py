"""
Atdork - Vulnerability Filter
Memfilter hasil pencarian berdasarkan signature platform/kerentanan (e.g., WordPress).
Digunakan untuk mengidentifikasi target yang berpotensi rentan.
"""

import re
import os
import logging
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)

# Cache untuk wordlist yang sudah dimuat
_wordlist_cache: Dict[str, List[re.Pattern]] = {}


def load_wordlist(path: str) -> List[re.Pattern]:
    """
    Memuat file wordlist yang berisi pola (satu per baris) dan mengkompilasi menjadi regex patterns.
    Baris kosong dan komentar (#) diabaikan.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Wordlist tidak ditemukan: {path}")

    patterns = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                patterns.append(re.compile(line, re.IGNORECASE))
            except re.error as e:
                logger.warning("Pola regex tidak valid di %s: %s (%s)", path, line, e)
    logger.info("Dimuat %d pola dari %s", len(patterns), path)
    return patterns


def get_wordlist(platform: str, wordlist_dir: str = "wordlists") -> List[re.Pattern]:
    """
    Mendapatkan daftar pola regex untuk platform tertentu.
    Menggunakan cache untuk menghindari pembacaan berulang.
    """
    if platform in _wordlist_cache:
        return _wordlist_cache[platform]

    # Tentukan path file wordlist
    filename = f"{platform}.txt"
    path = os.path.join(wordlist_dir, filename)
    patterns = load_wordlist(path)
    _wordlist_cache[platform] = patterns
    return patterns


def filter_vulnerable(
    results: List[Dict],
    platform: str = "wordpress",
    wordlist_dir: str = "wordlists"
) -> Tuple[List[Dict], List[Dict]]:
    """
    Memisahkan hasil menjadi dua kelompok: berpotensi rentan (vulnerable) dan aman (safe).

    Args:
        results: List hasil pencarian (dict dengan 'title', 'href', 'body').
        platform: Nama platform (default 'wordpress').
        wordlist_dir: Direktori tempat wordlist berada.

    Returns:
        Tuple (vulnerable_list, safe_list)
    """
    if not results:
        return [], []

    try:
        patterns = get_wordlist(platform, wordlist_dir)
    except FileNotFoundError as e:
        logger.error(str(e))
        # Jika wordlist tidak ada, anggap semua hasil safe
        return [], results

    vulnerable = []
    safe = []

    for res in results:
        # Gabungkan judul, URL, dan cuplikan untuk pencocokan
        text = f"{res.get('title','')} {res.get('href','')} {res.get('body','')}"
        if any(p.search(text) for p in patterns):
            vulnerable.append(res)
        else:
            safe.append(res)

    logger.info(
        "Filter %s: %d rentan, %d aman dari %d total hasil",
        platform, len(vulnerable), len(safe), len(results)
    )
    return vulnerable, safe
