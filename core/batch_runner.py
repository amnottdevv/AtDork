"""
Atdork - Batch Query Runner (Robust with Case Modules)
Menjalankan banyak dork sekaligus dengan progress bar, retry cerdas,
adaptive delay, fallback manager, circuit breaker, recovery strategy,
stats collector, concurrency, dan cache.

Semua interaksi dengan modul case/ dilindungi try-except agar
kegagalan di satu modul tidak merusak seluruh batch.

Arsitektur (v1.3.9.6):
    build_query_executor() membangun satu *executor* per-query yang dipakai
    OLEH run_batch() sekaligus oleh mode single-query di atdork.py, sehingga
    cache, resilient (circuit breaker/fallback/retry), adaptive delay, dan
    callback status (--resume) berjalan konsisten di kedua mode.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
)

from core.scanner import search_dork, SearchError
from lib.redactor import redact_proxy_url

try:
    from core.case.retry_handler import RetryAbort
except ImportError:  # pragma: no cover - modul case di repo selalu ada
    class RetryAbort(Exception):  # type: ignore[no-redef]
        """Fallback RetryAbort bila core.case.retry_handler tidak tersedia."""

logger = logging.getLogger(__name__)

# Durasi jeda saat FallbackManager memutuskan action "cooldown" (semua backend
# sedang rate-limited). Dipisah jadi konstanta agar bisa dioverride di test.
COOLDOWN_SLEEP_SECONDS = 30.0


# FIX HIGH: Define error classification fallback as a proper class
class ErrorCategory:
    """Error category constants for fallback when error_classifier unavailable."""
    FATAL = "fatal"
    TRANSIENT = "transient"
    RATE_LIMIT = "rate_limit"
    BLOCKED = "blocked"
    PROXY_FAIL = "proxy_fail"


def _get_error_classifier():
    """
    FIX HIGH: Safely import error classifier with fallback.
    Returns (classify_error function, ErrorCategory class)
    """
    try:
        from core.case.error_classifier import classify_error, ErrorCategory as EC
        logger.debug("Imported error_classifier from core.case")
        return classify_error, EC
    except ImportError:
        logger.warning("core.case.error_classifier not available, using fallback")
        # Fallback: classify all errors as FATAL for safety
        def fallback_classify(e):
            error_str = str(e).lower()
            if "429" in error_str or "rate" in error_str:
                return ErrorCategory.RATE_LIMIT
            elif "403" in error_str or "blocked" in error_str:
                return ErrorCategory.BLOCKED
            elif "proxy" in error_str:
                return ErrorCategory.PROXY_FAIL
            elif "timeout" in error_str or "transient" in error_str:
                return ErrorCategory.TRANSIENT
            else:
                return ErrorCategory.FATAL

        return fallback_classify, ErrorCategory


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
        logger.error("Batch file not found: %s", filepath)
        raise
    except Exception as e:
        logger.error("Failed to read batch file %s: %s", filepath, e)
        raise
    return queries


def parse_query_string(query_str: str, separator: str = ";") -> List[str]:
    """Pecah string menjadi beberapa query berdasarkan separator."""
    try:
        return [q.strip() for q in query_str.split(separator) if q.strip()]
    except Exception as e:
        logger.error("Failed to parse query string: %s", e)
        return []


# --------------------------------------------------------------------------- #
# Query executor (dipakai batch & single-query)
# --------------------------------------------------------------------------- #

def build_query_executor(
    search_kwargs: Dict[str, Any],
    case_modules: Optional[Dict] = None,
    *,
    cache=None,
    cache_params: Optional[Dict[str, Any]] = None,
    cache_ttl: int = 24,
    cache_only: bool = False,
    on_query_done: Optional[Callable[[str, list, bool], None]] = None,
    raise_on_error: bool = False,
    default_retry: bool = True,
) -> Callable[[str], List[Dict[str, Any]]]:
    """
    Bangun executor untuk menjalankan satu query pencarian.

    Args:
        search_kwargs: Parameter untuk search_dork (max_results, timeout,
            proxy_manager, region, backend, dll).
        case_modules: Dict instance modul case (circuit_breaker,
            fallback_manager, retry_handler, adaptive_delay, recovery_strategy,
            stats_collector).
        cache: Instance SearchCache opsional (dipakai untuk mode single-query
            dan batch sekaligus — perbaikan: sebelumnya cache hanya dipakai di
            mode single-query dan itu pun crash).
        cache_params: Parameter kunci cache (region, safesearch, dll).
        cache_ttl: TTL cache dalam jam.
        cache_only: Bila True, hanya layani dari cache (MISS → hasil kosong).
        on_query_done: Callback (query, results, success) yang dipanggil tepat
            sekali setiap query selesai — dipakai atdork.py untuk menandai
            status pending/completed/failed di SQLite (--resume).
        raise_on_error: Bila True, kegagalan total dilempar sebagai SearchError
            (mode single-query perlu exit code 1); bila False dikembalikan [].
        default_retry: Buat RetryHandler default bila case_modules tidak
            menyediakan (perilaku lama run_batch).

    Returns:
        Callable query -> list hasil. Query gagal bernilai [] (atau raise
        SearchError bila raise_on_error=True).
    """
    # ── Ambil modul case dengan aman ─────────────────────────────────
    circuit_breaker = None
    fallback_manager = None
    retry_handler = None
    adaptive_delay = None
    recovery_strategy = None
    stats_collector = None

    if case_modules and isinstance(case_modules, dict):
        try:
            circuit_breaker = case_modules.get("circuit_breaker")
            fallback_manager = case_modules.get("fallback_manager")
            retry_handler = case_modules.get("retry_handler")
            adaptive_delay = case_modules.get("adaptive_delay")
            recovery_strategy = case_modules.get("recovery_strategy")
            stats_collector = case_modules.get("stats_collector")
        except Exception as e:
            logger.warning("Failed to load case modules: %s. Continuing without case modules.", e)

    # ── Pastikan retry_handler tersedia ──────────────────────────────
    if retry_handler is None and default_retry:
        try:
            from core.case.retry_handler import RetryHandler
            retry_handler = RetryHandler(max_retries=2, base_delay=1.0)
            logger.info("RetryHandler created successfully as fallback")
        except ImportError:
            logger.warning("core.case.retry_handler not available. Retry disabled.")
            retry_handler = None
        except Exception as e:
            logger.warning("Failed to create default RetryHandler: %s", e)
            retry_handler = None

    # ── FIX HIGH: Import classifier dengan fallback yang lebih robust ──
    classify_error, ErrorCategory = _get_error_classifier()

    def execute(q: str) -> List[Dict[str, Any]]:
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
                logger.debug("Failed to get proxy: %s", e)
                current_proxy = None

        # ── Adaptive delay (sebelum request) ────────────────────────
        if adaptive_delay:
            try:
                adaptive_delay.wait(current_backend)
            except Exception as e:
                logger.debug("AdaptiveDelay.wait failed: %s", e)

        def _notify(results: list, success: bool) -> list:
            """Beritahu pemanggil (untuk penandaan status --resume)."""
            if on_query_done:
                try:
                    on_query_done(q, results, success)
                except Exception as e:
                    logger.warning("on_query_done failed for '%s': %s", q[:60], e)
            return results

        def _gate_backend() -> Optional[str]:
            """
            Pintu circuit breaker sebelum request.

            Returns None bila boleh lanjut, atau string alasan bila semua
            backend dalam kondisi OPEN (fail-fast, jangan di-hammer).
            """
            nonlocal current_backend
            if circuit_breaker is None:
                return None
            try:
                if circuit_breaker.allow(current_backend):
                    return None
                alt = (
                    fallback_manager.healthy_backend(exclude=current_backend)
                    if fallback_manager else None
                )
            except Exception as e:
                logger.warning("Circuit breaker gate failed: %s", e)
                return None

            if alt:
                logger.info(
                    "Circuit OPEN '%s' → switching to backend '%s'",
                    current_backend, alt,
                )
                current_backend = alt
                return None
            return (
                f"Circuit breaker OPEN for backend '{current_backend}' and no other "
                f"healthy backend — request aborted."
            )

        # ── Fungsi pencarian yang akan di-retry ──────────────────────
        def _fetch_results():
            reason = _gate_backend()
            if reason:
                raise SearchError(reason)
            # Hapus 'backend' dari kwargs agar tidak bentrok dengan argumen eksplisit
            kwargs = {k: v for k, v in search_kwargs.items() if k != 'backend'}
            # forced_proxy: terapkan proxy yang sudah dipilih/dirotasi oleh
            # keputusan FallbackManager (bug lama: proxy yang diambil diabaikan).
            return search_dork(
                q, backend=current_backend, forced_proxy=current_proxy, **kwargs
            )

        def _do_search():
            """Cache-aware wrapper di sekitar _fetch_results (berlaku untuk batch & single)."""
            if cache is None:
                return _fetch_results()
            if cache_only:
                cached = cache.get(q, current_backend, cache_params)
                if cached is None:
                    logger.debug(
                        "Cache-only MISS for '%s' (%s) → empty results", q[:50], current_backend
                    )
                    return []
                return cached
            return cache.get_or_set(
                q,
                current_backend,
                _fetch_results,
                params=cache_params,
                ttl_hours=cache_ttl,
            )

        # ── Callback saat retry ──────────────────────────────────────
        def _on_retry(attempt, exception):
            nonlocal current_backend, current_proxy
            try:
                category = classify_error(exception)
            except Exception as e:
                logger.debug("Error during classify_error: %s, using FATAL", e)
                category = ErrorCategory.FATAL

            logger.debug("Retry attempt %d after error %s: %s", attempt, category, exception)

            # Selalu catat kegagalan ke circuit breaker untuk backend saat ini
            if circuit_breaker:
                try:
                    circuit_breaker.record_failure(current_backend)
                    if stats_collector:
                        try:
                            stats_collector.record_circuit_breaker(
                                opened=circuit_breaker.status(current_backend) == "OPEN"
                            )
                        except Exception as e:
                            logger.debug("StatsCollector.record_circuit_breaker failed: %s", e)
                except Exception as e:
                    logger.debug("CircuitBreaker.record_failure failed: %s", e)

            # Recovery strategy (jika tersedia) – memberikan saran tindakan
            if recovery_strategy:
                try:
                    recovery_action = recovery_strategy.get_action(
                        error_category=category,
                        backend=current_backend,
                        proxy=current_proxy,
                    )
                    logger.debug("Recovery strategy suggests: %s", recovery_action.get("action"))
                except Exception as e:
                    logger.warning("RecoveryStrategy.get_action failed: %s", e)

            # ── Fallback manager ──────────────────────────────────────
            # Keputusan dihitung TERPISAH dari penerapannya agar action
            # "abort" tidak lagi tertelan oleh except blok ini (bug lama:
            # `raise exception` ada di dalam try yang sama → retry tetap jalan).
            decision = None
            if fallback_manager and circuit_breaker:
                try:
                    decision = fallback_manager.decide(
                        current_backend=current_backend,
                        current_proxy=current_proxy,
                        error_category=category,
                    )
                except Exception as e:
                    logger.warning("FallbackManager.decide failed: %s", e)
                    decision = None

            if decision:
                action = decision.get("action")
                if action == "switch_backend":
                    new_backend = decision.get("next_backend") or current_backend
                    if new_backend != current_backend:
                        logger.info("Fallback: switching backend %s → %s", current_backend, new_backend)
                        current_backend = new_backend
                elif action == "rotate_proxy":
                    next_proxy = decision.get("next_proxy")
                    if next_proxy:
                        # Bug lama: next_proxy hanya di-log, tidak pernah
                        # dipakai. Sekarang dipakai oleh search_dork lewat
                        # forced_proxy pada percobaan berikutnya.
                        logger.info("Fallback: rotating proxy → %s", redact_proxy_url(next_proxy))
                        current_proxy = next_proxy
                    else:
                        logger.info("Fallback: rotating proxy")
                elif action == "cooldown":
                    logger.info("Fallback: cooldown, pausing for %.0f seconds", COOLDOWN_SLEEP_SECONDS)
                    time.sleep(COOLDOWN_SLEEP_SECONDS)
                elif action == "abort":
                    reason = decision.get("reason") or "FallbackManager decided to abort"
                    logger.error("Fallback: abort — %s", reason)
                    raise RetryAbort(reason)

            # Adaptive delay laporkan error
            if adaptive_delay:
                try:
                    status_code = 429 if "429" in str(exception) else 500
                    adaptive_delay.report(current_backend, status_code, False)
                except Exception as e:
                    logger.debug("AdaptiveDelay.report failed: %s", e)

            # Catat retry ke stats collector
            if stats_collector:
                try:
                    stats_collector.record_retry(success=False)
                except Exception as e:
                    logger.debug("StatsCollector.record_retry failed: %s", e)

        # ── Callback saat menyerah ───────────────────────────────────
        def _on_giveup(exception):
            if adaptive_delay:
                try:
                    status_code = 429 if "429" in str(exception) else 500
                    adaptive_delay.report(current_backend, status_code, False)
                except Exception as e:
                    logger.debug("AdaptiveDelay.report failed: %s", e)
            if stats_collector:
                try:
                    stats_collector.record_fallback(success=False)
                except Exception as e:
                    logger.debug("StatsCollector.record_fallback failed: %s", e)

        def _record_backend_failure():
            if stats_collector:
                try:
                    stats_collector.record_backend(current_backend, 500, False)
                except Exception as e:
                    logger.debug("StatsCollector.record_backend failed: %s", e)

        # ── Jalankan dengan atau tanpa retry handler ─────────────────
        result: Optional[list] = None
        error: Optional[BaseException] = None

        if retry_handler:
            try:
                result, final_error = retry_handler.execute(
                    _do_search,
                    on_retry=_on_retry,
                    on_giveup=_on_giveup,
                )
                if final_error is not None:
                    error = final_error
                    result = None
            except Exception as e:  # kegagalan tak terduga dari modul case
                error = e
                result = None
        else:
            try:
                result = _do_search()
            except Exception as e:
                error = e
                result = None

        if error is not None:
            logger.error("'%s' failed: %s", q[:60], error)
            _record_backend_failure()
            if raise_on_error:
                _notify([], False)
                raise SearchError(f"Query '{q[:60]}' failed: {error}") from error
            return _notify([], False)

        # Sukses → catat ke circuit breaker, adaptive delay, stats collector
        if circuit_breaker:
            try:
                circuit_breaker.record_success(current_backend)
                if current_proxy:
                    circuit_breaker.record_success(current_proxy)
            except Exception as e:
                logger.debug("CircuitBreaker.record_success failed: %s", e)
        if adaptive_delay:
            try:
                adaptive_delay.report(current_backend, 200, len(result) > 0)
            except Exception as e:
                logger.debug("AdaptiveDelay.report failed: %s", e)
        if stats_collector:
            try:
                stats_collector.record_backend(current_backend, 200, len(result) > 0)
                if retry_handler:
                    stats_collector.record_retry(success=True)
            except Exception as e:
                logger.debug("StatsCollector.record_backend/retry failed: %s", e)

        return _notify(result or [], True)

    return execute


# --------------------------------------------------------------------------- #
# Batch runner
# --------------------------------------------------------------------------- #

def run_batch(
    queries: List[str],
    case_modules: Optional[Dict] = None,
    concurrency: int = 1,
    *,
    cache=None,
    cache_params: Optional[Dict[str, Any]] = None,
    cache_ttl: int = 24,
    cache_only: bool = False,
    on_query_done: Optional[Callable[[str, list, bool], None]] = None,
    **search_kwargs,
) -> Dict[str, list]:
    """
    Jalankan pencarian untuk setiap query dengan dukungan modul case & cache.

    Args:
        queries: Daftar query.
        case_modules: Dictionary berisi instance modul case (circuit_breaker, fallback_manager,
                     retry_handler, adaptive_delay, recovery_strategy, stats_collector).
        concurrency: Jumlah thread paralel (1 = sekuensial).
        cache: SearchCache opsional — hasil batch kini ikut di-cache (bug lama:
            cache diabaikan total di mode batch).
        cache_params: Parameter kunci cache.
        cache_ttl: TTL cache dalam jam.
        cache_only: Hanya layani dari cache (MISS → []).
        on_query_done: Callback (query, results, success) per query selesai.
        **search_kwargs: Parameter untuk search_dork (max_results, timeout, proxy_manager, dll).

    Returns:
        Dictionary {query: [list of result dicts]}. Query yang gagal bernilai list kosong.

    Catatan:
        Jika `queries` mengandung duplikat (baris yang sama persis muncul lebih
        dari sekali), duplikat tersebut hanya akan dieksekusi SEKALI. Ini untuk
        menghindari pemborosan request/rate-limit karena mencari dork yang identik
        berkali-kali — hasilnya akan tetap sama untuk query yang sama persis.
    """
    results: Dict[str, list] = {}
    if not queries:
        return results

    # kemunculan pertama sekaligus membuang duplikat.
    unique_queries = list(dict.fromkeys(queries))
    duplicate_count = len(queries) - len(unique_queries)
    if duplicate_count > 0:
        logger.warning(
            "%d duplicate queries detected in batch; each unique query will run only once.",
            duplicate_count,
        )

    total = len(unique_queries)

    execute = build_query_executor(
        search_kwargs,
        case_modules,
        cache=cache,
        cache_params=cache_params,
        cache_ttl=cache_ttl,
        cache_only=cache_only,
        on_query_done=on_query_done,
        raise_on_error=False,
        default_retry=True,
    )

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
                    executor.submit(execute, q): q for q in unique_queries
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
            for idx, q in enumerate(unique_queries, 1):
                desc = q if len(q) <= 60 else q[:57] + "..."
                progress.update(task, description=f"[{idx}/{total}] {desc}")
                try:
                    res = execute(q)
                except Exception as e:
                    logger.error("'%s' failed completely: %s", q[:60], e)
                    res = []
                results[q] = res
                progress.advance(task)

    # ── Tampilkan statistik jika stats collector tersedia ────────────
    if case_modules and isinstance(case_modules, dict) and case_modules.get("stats_collector"):
        stats_collector = case_modules["stats_collector"]
        try:
            summary = stats_collector.summary()
            # Gunakan console dari rich jika tersedia, jika tidak gunakan logger
            try:
                from rich.console import Console
                Console().print(summary)
            except ImportError:
                logger.info(summary)
        except Exception as e:
            logger.warning("Failed to display statistics: %s", e)

    return results
