"""
Atdork - Multi-Threaded Batch Runner with Fallback
Menjalankan banyak query secara paralel (multi-threading) dengan deteksi
kegagalan berturut-turut dan fallback otomatis ke mode sequential.
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from typing import List, Dict, Optional

from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
)

from core.scanner import search_dork

logger = logging.getLogger(__name__)

# Global lock untuk progress bar (jika dipakai)
_progress_lock = threading.Lock()


def run_batch_multithread(
    queries: List[str],
    concurrency: int = 5,
    fallback_sequential: bool = True,
    max_consecutive_failures: int = 3,
    **kwargs,
) -> Dict[str, list]:
    """
    Jalankan batch queries menggunakan thread pool dengan fallback.

    Args:
        queries: Daftar query string.
        concurrency: Jumlah maksimal worker thread (default 5).
        fallback_sequential: Jika True, ketika terjadi kegagalan berturut-turut
            melebihi max_consecutive_failures, turunkan concurrency atau beralih
            ke sequential murni.
        max_consecutive_failures: Ambang kegagalan berturut-turut sebelum fallback.
        **kwargs: Parameter yang diteruskan ke search_dork (max_results, timeout,
                  retries, delay, proxy_manager, region, safesearch, timelimit,
                  backend, user_agent).

    Returns:
        Dictionary {query: list of result dicts}.
        Query yang gagal akan bernilai list kosong [].
    """
    if not queries:
        return {}

    total = len(queries)
    results: Dict[str, list] = {}
    original_concurrency = concurrency

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task(
            f"[cyan]Running {total} queries (threads={concurrency})...",
            total=total,
        )

        consecutive_failures = 0
        current_concurrency = concurrency
        use_parallel = current_concurrency > 1

        while True:  # akan keluar setelah selesai
            if use_parallel:
                # Jalankan dengan thread pool
                with ThreadPoolExecutor(max_workers=current_concurrency) as executor:
                    future_to_query = {
                        executor.submit(search_dork, query=q, **kwargs): q
                        for q in queries
                    }

                    try:
                        for future in as_completed(future_to_query):
                            q = future_to_query[future]
                            try:
                                res = future.result()
                                results[q] = res
                                consecutive_failures = 0
                                logger.debug(f"'{q[:60]}' -> {len(res)} hasil")
                            except Exception as e:
                                logger.error(f"'{q[:60]}' gagal: {e}")
                                results[q] = []
                                consecutive_failures += 1

                            with _progress_lock:
                                progress.advance(task)

                            # Cek apakah perlu fallback
                            if fallback_sequential and consecutive_failures >= max_consecutive_failures:
                                logger.warning(
                                    f"{consecutive_failures} kegagalan berturut-turut, "
                                    "menurunkan ke mode sequential."
                                )
                                # Batalkan semua future yang belum selesai
                                for f in future_to_query:
                                    f.cancel()
                                # Tandai query yang belum selesai sebagai gagal
                                for pending_q in set(queries) - set(results.keys()):
                                    results[pending_q] = []
                                    with _progress_lock:
                                        progress.advance(task)
                                use_parallel = False
                                break
                    except Exception as pool_error:
                        logger.error(f"Thread pool error: {pool_error}")
                        # Fallback ke sequential
                        for pending_q in set(queries) - set(results.keys()):
                            results[pending_q] = []
                            with _progress_lock:
                                progress.advance(task)
                        use_parallel = False

            if not use_parallel:
                # Sequential fallback untuk sisa query yang belum dikerjakan
                remaining = [q for q in queries if q not in results]
                if not remaining:
                    break
                logger.info(f"Melanjutkan {len(remaining)} query secara sequential.")
                progress.update(task, description=f"[yellow]Sequential fallback ({len(remaining)} queries)...")
                for q in remaining:
                    try:
                        res = search_dork(q, **kwargs)
                        results[q] = res
                        logger.debug(f"'{q[:60]}' -> {len(res)} hasil")
                    except Exception as e:
                        logger.error(f"'{q[:60]}' gagal: {e}")
                        results[q] = []
                    with _progress_lock:
                        progress.advance(task)
                break

            # Jika parallel selesai tanpa fallback
            if len(results) >= total:
                break
            # Jika parallel berhenti tapi belum semua (karena fallback sudah break), loop akan lanjut ke sequential

    return results
