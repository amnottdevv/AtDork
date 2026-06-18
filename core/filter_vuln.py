"""
Atdork - Vulnerability Filter
Memfilter hasil pencarian berdasarkan signature platform/kerentanan.
Sekarang mendukung wordlist dinamis: nama file = {arg}.txt, dengan deteksi otomatis tipe '-link'.
"""

import re
import os
import logging
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)

# Cache: key = path file absolut, value = list of compiled regex patterns
_wordlist_cache: Dict[str, List[re.Pattern]] = {}


def resolve_filter_arg(filter_arg: str, wordlist_dir: str = "wordlists") -> Tuple[str, str, str]:
    """
    Memeriksa keberadaan file wordlist, menentukan tipe filter, dan mengembalikan informasi.

    Args:
        filter_arg: Nilai dari flag --filter-vuln (misal 'wordpress', 'joomla-link')
        wordlist_dir: Direktori tempat wordlist berada

    Returns:
        Tuple (base_name, filter_type, filepath)
        - base_name: nama platform tanpa akhiran '-link' (untuk keperluan label)
        - filter_type: 'link' atau 'path'
        - filepath: path absolut ke file wordlist

    Raises:
        FileNotFoundError: Jika file tidak ditemukan, dengan pesan error yang jelas
    """
    # Bentuk nama file dan path
    filename = f"{filter_arg}.txt"
    filepath = os.path.join(wordlist_dir, filename)

    if not os.path.isfile(filepath):
        error_msg = [
            f"❌ Error: Wordlist file '{filename}' TIDAK DITEMUKAN",
            f"   Direktori yang dicek: '{os.path.abspath(wordlist_dir)}/'"
        ]

        # Cek kemungkinan typo: jika user memanggil tanpa '-link', tapi ada file dengan '-link'
        if filter_arg.endswith("-link"):
            base = filter_arg[:-5]  # buang '-link'
            base_path = os.path.join(wordlist_dir, f"{base}.txt")
            if os.path.exists(base_path):
                error_msg.append(f"   💡 Tip: Ditemukan '{base}.txt'. Apakah maksud Anda '--filter-vuln {base}'?")
        else:
            link_path = os.path.join(wordlist_dir, f"{filter_arg}-link.txt")
            if os.path.exists(link_path):
                error_msg.append(f"   💡 Tip: Ditemukan '{filter_arg}-link.txt'. Apakah maksud Anda '--filter-vuln {filter_arg}-link'?")

        raise FileNotFoundError("\n".join(error_msg))

    # Tentukan tipe filter berdasarkan akhiran
    if filter_arg.endswith("-link") or filter_arg.endswith("-url"):
        filter_type = "link"
        base_name = re.sub(r"-(link|url)$", "", filter_arg)
    else:
        filter_type = "path"
        base_name = filter_arg

    return base_name, filter_type, filepath


def load_wordlist(path: str) -> List[re.Pattern]:
    """
    Memuat file wordlist dan mengkompilasi setiap baris menjadi regex pattern.
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


def get_wordlist(filter_arg: str, wordlist_dir: str = "wordlists") -> List[re.Pattern]:
    """
    Mendapatkan daftar pola regex untuk argumen filter tertentu.
    Menggunakan cache berdasarkan path file untuk efisiensi.

    Args:
        filter_arg: Nilai flag --filter-vuln (misal 'wordpress', 'joomla-link')
        wordlist_dir: Direktori wordlist

    Returns:
        List of compiled regex patterns
    """
    # Resolve path file dan tipe (base_name, filter_type tidak digunakan di sini, tapi dipakai untuk validasi)
    base_name, filter_type, filepath = resolve_filter_arg(filter_arg, wordlist_dir)

    # Cache berdasarkan filepath absolut
    abs_path = os.path.abspath(filepath)
    if abs_path in _wordlist_cache:
        return _wordlist_cache[abs_path]

    patterns = load_wordlist(abs_path)
    _wordlist_cache[abs_path] = patterns
    return patterns


def get_filter_info(filter_arg: str, wordlist_dir: str = "wordlists") -> Tuple[List[re.Pattern], str, str]:
    """
    Mengembalikan (patterns, filter_type, base_name) untuk argumen filter.

    Berguna jika caller membutuhkan tipe filter (misal untuk menentukan cara memproses hasil).
    """
    base_name, filter_type, filepath = resolve_filter_arg(filter_arg, wordlist_dir)
    patterns = get_wordlist(filter_arg, wordlist_dir)  # memanfaatkan cache
    return patterns, filter_type, base_name


def filter_vulnerable(
    results: List[Dict],
    filter_arg: str = "wordpress",
    wordlist_dir: str = "wordlists"
) -> Tuple[List[Dict], List[Dict], str]:
    """
    Memisahkan hasil menjadi dua kelompok: berpotensi rentan (vulnerable) dan aman (safe).

    Args:
        results: List hasil pencarian (dict dengan 'title', 'href', 'body').
        filter_arg: Nilai flag --filter-vuln (misal 'wordpress', 'joomla-link')
        wordlist_dir: Direktori tempat wordlist berada.

    Returns:
        Tuple (vulnerable_list, safe_list, filter_type)
        - filter_type: 'link' atau 'path' (bisa digunakan untuk keperluan lanjutan)
    """
    if not results:
        return [], [], "unknown"

    try:
        patterns, filter_type, base_name = get_filter_info(filter_arg, wordlist_dir)
    except FileNotFoundError as e:
        logger.error(str(e))
        # Jika wordlist tidak ada, anggap semua hasil safe
        return [], results, "unknown"

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
        "Filter %s (tipe %s): %d rentan, %d aman dari %d total hasil",
        filter_arg, filter_type, len(vulnerable), len(safe), len(results)
    )
    return vulnerable, safe, filter_type
