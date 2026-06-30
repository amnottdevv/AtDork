"""
Atdork - Batch Query Runner (Robust with Case Modules)
Menjalankan banyak dork sekaligus dengan progress bar, retry cerdas,
adaptive delay, fallback manager, circuit breaker, dan concurrency.

Semua interaksi dengan modul case/ dilindungi try-except agar
kegagalan di satu modul tidak merusak seluruh batch.
"""

import logging
import time
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

logger = logging.getLogger(__name__)


def load_queries_from_file(filepath: str) -> List[str]:
    """Baca file teks, satu query per baris. Abaikan baris kosong dan komentar."""
    queries = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                queries.append(line)
    except FileNotFoundError:
        logger.error("File batch tidak ditemukan: %s", filepath)
        raise
    except Exception as e:
        logger.error("Gagal membaca file batch %s: %s", filepath, e)
        raise
    return queries


def parse_query_string(query_str: str, separator: str = ";") -> List[str]:
    """Pecah string menjadi beberapa query berdasarkan separator."""
    try:
        return [q.strip() for q in query_str.split(separator) if q.strip()]
    except Exception as e:
        logger.error("Gagal parsing query string: %s", e)
        return []


def run_batch(
    queries: List[str],
    case_modules: Optional[Dict] = None,
    concurrency: int = 1,
    **search_kwargs,
) -> Dict[str, list]:
    """
    Jalankan pencarian untuk setiap query dengan dukungan modul case.

    Args:
        queries: Daftar query.
        case_modules: Dictionary berisi instance modul case (circuit_breaker, fallback_manager, retry_handler, adaptive_delay).
        concurrency: Jumlah thread paralel (1 = sekuensial).
        **search_kwargs: Parameter untuk search_dork (max_results, timeout, proxy_manager, dll).

    Returns:
        Dictionary {query: [list of result dicts]}. Query yang gagal bernilai list kosong.
    """
    results: Dict[str, list] = {}
    total = len(queries)
    if total == 0:
        return results

    # ── Ambil modul case dengan aman ─────────────────────────────────
    circuit_breaker = None
    fallback_manager = None
    retry_handler = None
    adaptive_delay = None

    if case_modules and isinstance(case_modules, dict):
        try:
            circuit_breaker = case_modules.get("circuit_breaker")
            fallback_manager = case_modules.get("fallback_manager")
            retry_handler = case_modules.get("retry_handler")
            adaptive_delay = case_modules.get("adaptive_delay")
        except Exception as e:
            logger.warning("Gagal mengambil modul case: %s. Melanjutkan tanpa modul case.", e)

    # ── Pastikan retry_handler tersedia ──────────────────────────────
    if retry_handler is None:
        try:
            from core.case.retry_handler import RetryHandler
            retry_handler = RetryHandler(max_retries=2, base_delay=1.0)
        except ImportError:
            logger.warning("core.case.retry_handler tidak tersedia. Retry dinonaktifkan.")
            retry_handler = None
        except Exception as e:
            logger.warning("Gagal membuat RetryHandler default: %s", e)
            retry_handler = None

    # ── Import classifier (fallback) ──────────────────────────────────
    try:
        from core.case.error_classifier import classify_error, ErrorCategory
    except ImportError:
        classify_error = lambda e: "fatal"  # noqa
        ErrorCategory = type('ErrorCategory', (), {'FATAL': 'fatal', 'TRANSIENT': 'transient', 'RATE_LIMIT': 'rate_limit', 'BLOCKED': 'blocked', 'PROXY_FAIL': 'proxy_fail'})

    # ── Fungsi eksekusi per query ────────────────────────────────────
    def _execute_single(q: str) -> list:
        """Eksekusi satu query dengan proteksi penuh terhadap error modul case."""
        backend = search_kwargs.get("backend", "auto")
        current_backend = backend
        current_proxy = None

        # Ambil proxy dengan aman
        proxy_manager = search_kwargs.get("proxy_manager")
        if proxy_manager:
            try:
                current_proxy = proxy_manager.get_proxy()
            except Exception as e:
                logger.debug("Gagal mengambil proxy: %s", e)
                current_proxy = None

        # ── Adaptive delay (sebelum request) ────────────────────────
        if adaptive_delay:
            try:
                adaptive_delay.wait(current_backend)
            except Exception as e:
                logger.debug("AdaptiveDelay.wait gagal: %s", e)

        # ── Fungsi pencarian yang akan di-retry ──────────────────────
        def _do_search():
            # Hapus 'backend' dari kwargs agar tidak bentrok dengan argumen eksplisit
            kwargs = {k: v for k, v in search_kwargs.items() if k != 'backend'}
            return search_dork(q, backend=current_backend, **kwargs)

        # ── Callback saat retry ──────────────────────────────────────
        def _on_retry(attempt, exception):
            nonlocal current_backend, current_proxy
            try:
                category = classify_error(exception)
            except Exception:
                category = ErrorCategory.FATAL

            logger.debug("Retry attempt %d setelah error %s: %s", attempt, category, exception)

            # Fallback manager
            if fallback_manager and circuit_breaker:
                try:
                    decision = fallback_manager.decide(
                        current_backend=current_backend,
                        current_proxy=current_proxy,
                        error_category=category,
                    )
                    action = decision.get("action")
                    if action == "switch_backend":
                        new_backend = decision.get("next_backend", current_backend)
                        logger.info("Fallback: ganti backend %s → %s", current_backend, new_backend)
                        current_backend = new_backend
                    elif action == "rotate_proxy":
                        logger.info("Fallback: rotasi proxy")
                    elif action == "cooldown":
                        logger.info("Fallback: cooldown, jeda 30 detik")
                        time.sleep(30)
                    elif action == "abort":
                        logger.error("Fallback: abort, tidak bisa melanjutkan")
                        raise exception
                except Exception as e:
                    logger.warning("FallbackManager.decide gagal: %s", e)

            # Adaptive delay laporkan error
            if adaptive_delay:
                try:
                    status_code = 429 if "429" in str(exception) else 500
                    adaptive_delay.report(current_backend, status_code, False)
                except Exception as e:
                    logger.debug("AdaptiveDelay.report gagal: %s", e)

        # ── Callback saat menyerah ───────────────────────────────────
        def _on_giveup(exception):
            if adaptive_delay:
                try:
                    adaptive_delay.report(current_backend, 500, False)
                except Exception as e:
                    logger.debug("AdaptiveDelay.report gagal: %s", e)

        # ── Jalankan dengan atau tanpa retry handler ─────────────────
        if retry_handler:
            try:
                result, final_error = retry_handler.execute(
                    _do_search,
                    on_retry=_on_retry,
                    on_giveup=_on_giveup,
                )
                if final_error:
                    logger.error("'%s' gagal setelah retry: %s", q[:60], final_error)
                    return []

                # Sukses → catat ke circuit breaker & adaptive delay
                if circuit_breaker:
                    try:
                        circuit_breaker.record_success(current_backend)
                        if current_proxy:
                            circuit_breaker.record_success(current_proxy)
                    except Exception as e:
                        logger.debug("CircuitBreaker.record_success gagal: %s", e)
                if adaptive_delay:
                    try:
                        adaptive_delay.report(current_backend, 200, len(result) > 0)
                    except Exception as e:
                        logger.debug("AdaptiveDelay.report gagal: %s", e)
                return result
            except Exception as e:
                logger.error("'%s' gagal tak terduga: %s", q[:60], e)
                return []
        else:
            # Tanpa retry handler → langsung panggil search_dork
            try:
                kwargs = {k: v for k, v in search_kwargs.items() if k != 'backend'}
                result = search_dork(q, backend=current_backend, **kwargs)
                if adaptive_delay:
                    try:
                        adaptive_delay.report(current_backend, 200, len(result) > 0)
                    except Exception:
                        pass
                if circuit_breaker:
                    try:
                        circuit_breaker.record_success(current_backend)
                        if current_proxy:
                            circuit_breaker.record_success(current_proxy)
                    except Exception:
                        pass
                return result
            except Exception as e:
                logger.error("'%s' gagal: %s", q[:60], e)
                return []

    # ── Progress bar & eksekusi ──────────────────────────────────────
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("[cyan]Running batch queries...", total=total)

        if concurrency > 1:
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
            for idx, q in enumerate(queries, 1):
                desc = q if len(q) <= 60 else q[:57] + "..."
                progress.update(task, description=f"[{idx}/{total}] {desc}")
                try:
                    res = _execute_single(q)
                except Exception as e:
                    logger.error("'%s' gagal total: %s", q[:60], e)
                    res = []
                results[q] = res
                progress.advance(task)

    return results
