"""
Atdork - Batch Query Runner (Enhanced with Resilience & Rate Limiter)
Menjalankan banyak dork sekaligus (dari file atau string) dengan progress bar,
dukungan resilience handler, rate limiter adaptif, dan eksekusi paralel.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional

from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
)

from core.scanner import search_dork
from core.case.resilience import ResilienceHandler
from core.case.rate_limiter import RateLimiter

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


def run_batch(
    queries: List[str],
    resilience_handler: Optional[ResilienceHandler] = None,
    rate_limiter: Optional[RateLimiter] = None,
    concurrency: int = 1,
    **kwargs,
) -> Dict[str, list]:
    """
    Jalankan pencarian untuk setiap query.

    Args:
        queries: Daftar query string.
        resilience_handler: Instance ResilienceHandler (opsional, untuk mode tahan banting).
        rate_limiter: Instance RateLimiter (opsional, untuk delay adaptif).
        concurrency: Jumlah thread paralel (1 = sekuensial).
        **kwargs: Diteruskan ke search_dork (atau resilience_handler.execute).

    Returns:
        Dictionary {query: [list of result dicts]}.
        Query yang gagal akan bernilai list kosong [].
    """
    results = {}
    total = len(queries)
    if total == 0:
        return results

    def _execute_single(q: str) -> list:
        """
        Wrapper yang menangani resilience, rate limiting, dan fallback.
        Mengembalikan list hasil (kosong jika gagal).
        """
        backend = kwargs.get("backend", "auto")
        if rate_limiter:
            rate_limiter.wait(backend)

        if resilience_handler:
            # Resilience handler mengembalikan tuple (results, error_message)
            res, err = resilience_handler.execute(q, **kwargs)
            if err:
                if rate_limiter:
                    # Klasifikasi error sederhana untuk rate limiter
                    if "429" in str(err):
                        rate_limiter.report_response(backend, 429, False)
                    else:
                        rate_limiter.report_response(backend, 500, False)
                logger.error("'%s' gagal: %s", q[:60], err)
                return []
            if rate_limiter:
                rate_limiter.report_response(backend, 200, len(res) > 0)
            return res
        else:
            try:
                res = search_dork(q, **kwargs)
                if rate_limiter:
                    rate_limiter.report_response(backend, 200, len(res) > 0)
                return res
            except Exception as e:
                if rate_limiter:
                    if "429" in str(e):
                        rate_limiter.report_response(backend, 429, False)
                    else:
                        rate_limiter.report_response(backend, 500, False)
                logger.error("'%s' gagal: %s", q[:60], e)
                return []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("[cyan]Running batch queries...", total=total)

        if concurrency > 1:
            # Parallel execution
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                future_to_query = {
                    executor.submit(_execute_single, q): q for q in queries
                }
                for future in as_completed(future_to_query):
                    q = future_to_query[future]
                    try:
                        res = future.result()
                    except Exception as e:
                        logger.error("'%s' failed unexpectedly: %s", q[:60], e)
                        res = []
                    results[q] = res
                    progress.update(task, advance=1)
        else:
            # Sequential execution
            for idx, q in enumerate(queries, 1):
                desc = q if len(q) <= 60 else q[:57] + "..."
                progress.update(task, description=f"[{idx}/{total}] {desc}")
                res = _execute_single(q)
                results[q] = res
                progress.advance(task)

    return results
