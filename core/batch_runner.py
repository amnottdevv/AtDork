"""
Atdork - Batch Query Runner
Menjalankan banyak dork sekaligus (dari file atau string) dengan progress bar.
"""

import logging
from typing import List, Dict

from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
)

from core.scanner import search_dork

logger = logging.getLogger(__name__)


def load_queries_from_file(filepath: str) -> List[str]:
    """
    Baca file teks, satu query per baris.
    Abaikan baris kosong dan baris yang diawali '#'.
    """
    queries = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            queries.append(line)
    return queries


def parse_query_string(query_str: str, separator: str = ";") -> List[str]:
    """
    Pecah string menjadi beberapa query berdasarkan separator.
    Default separator ';'.
    """
    return [q.strip() for q in query_str.split(separator) if q.strip()]


def run_batch(queries: List[str], **kwargs) -> Dict[str, list]:
    """
    Jalankan pencarian untuk setiap query secara berurutan.
    kwargs diteruskan ke search_dork (max_results, timeout, retries, delay,
    proxy, region, safesearch, timelimit, backend, user_agent).

    Returns:
        Dictionary {query: [list of result dicts]}.
        Query yang gagal akan bernilai list kosong [].
    """
    results = {}
    total = len(queries)
    if total == 0:
        return results

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("[cyan]Running batch queries...", total=total)

        for idx, q in enumerate(queries, 1):
            desc = q if len(q) <= 60 else q[:57] + "..."
            progress.update(task, description=f"[{idx}/{total}] {desc}")

            try:
                res = search_dork(q, **kwargs)
                results[q] = res
                logger.debug(f"'{desc}' -> {len(res)} hasil")
            except Exception as e:
                logger.error(f"'{desc}' gagal: {e}")
                results[q] = []

            progress.advance(task)

    return results