"""
Unit tests untuk wiring --resilient (circuit breaker, fallback manager,
retry handler, recovery strategy, stats collector).

Regresi v1.3.9.6:
  - circuit breaker.allow() tidak pernah dipanggil (backend tetap di-hammer);
  - keputusan FallbackManager 'abort' tertelan oleh except sendiri sehingga
    retry tetap jalan;
  - next_proxy dari keputusan rotasi tidak pernah dipakai;
  - modul case diabaikan total oleh path single-query.
"""

from unittest.mock import MagicMock, patch

import pytest

import atdork
from core.batch_runner import build_query_executor, run_batch
from core.case.circuit_breaker import CircuitBreaker
from core.case.fallback_manager import FallbackManager
from core.case.retry_handler import RetryHandler, RetryAbort
from core.proxy_manager import ProxyManager


@pytest.fixture(autouse=True)
def fast_cooldown(monkeypatch):
    monkeypatch.setattr("core.batch_runner.COOLDOWN_SLEEP_SECONDS", 0.0)


def _case(**over):
    modules = {
        "circuit_breaker": None,
        "ip_guard": None,
        "fallback_manager": None,
        "retry_handler": None,
        "adaptive_delay": None,
        "recovery_strategy": None,
        "stats_collector": None,
    }
    modules.update(over)
    return modules


# ── Pintu circuit breaker ─────────────────────────────────────────────────

@patch("core.batch_runner.search_dork")
def test_circuit_open_without_fallback_fails_fast(mock_search):
    """Circuit OPEN dan tidak ada pengganti → jangan kirim request sama sekali."""
    cb = CircuitBreaker(threshold=1, cooldown=120.0)
    cb.record_failure("duckduckgo")  # → OPEN

    seen = []
    execute = build_query_executor(
        {"backend": "duckduckgo"},
        _case(circuit_breaker=cb, retry_handler=RetryHandler(max_retries=0)),
        on_query_done=lambda q, r, ok: seen.append(ok),
    )
    results = execute("q1")

    mock_search.assert_not_called()
    assert results == []
    assert seen == [False]
    assert cb.status("duckduckgo") == "OPEN"


@patch("core.batch_runner.search_dork")
def test_circuit_open_switches_to_healthy_backend(mock_search):
    """Circuit OPEN → request dialihkan ke backend sehat (allow() dipakai!)."""
    cb = CircuitBreaker(threshold=1, cooldown=120.0)
    cb.record_failure("duckduckgo")  # → OPEN
    fm = FallbackManager(backends=["duckduckgo", "startpage"], circuit_breaker=cb)
    mock_search.return_value = [{"title": "ok", "href": "http://a.com", "body": ""}]

    execute = build_query_executor(
        {"backend": "duckduckgo"},
        _case(circuit_breaker=cb, fallback_manager=fm,
              retry_handler=RetryHandler(max_retries=0)),
    )
    results = execute("q1")

    assert results
    assert mock_search.call_args.kwargs["backend"] == "startpage"


@patch("core.batch_runner.search_dork")
def test_all_circuits_open_no_hammering(mock_search):
    """Semua backend OPEN → fail-fast, search_dork tidak dipanggil."""
    cb = CircuitBreaker(threshold=1, cooldown=120.0)
    cb.record_failure("duckduckgo")
    cb.record_failure("startpage")
    fm = FallbackManager(backends=["duckduckgo", "startpage"], circuit_breaker=cb)

    execute = build_query_executor(
        {"backend": "duckduckgo"},
        _case(circuit_breaker=cb, fallback_manager=fm,
              retry_handler=RetryHandler(max_retries=0)),
    )
    assert execute("q1") == []
    mock_search.assert_not_called()
    assert cb.status("startpage") == "OPEN"


# ── Keputusan abort harus benar-benar berhenti ────────────────────────────

def test_retry_abort_stops_retry_unit():
    calls = []

    def func():
        calls.append(1)
        raise Exception("timeout")

    def on_retry(attempt, exc):
        raise RetryAbort("cukup!")

    rh = RetryHandler(max_retries=5, base_delay=0.0)
    result, err = rh.execute(func, on_retry=on_retry)
    assert result is None
    assert isinstance(err, RetryAbort)
    assert len(calls) == 1  # tidak ada retry lagi


@patch("core.batch_runner.search_dork")
def test_fallback_abort_decision_stops_batch(mock_search):
    """Regresi: action 'abort' dikecualikan oleh except-nya sendiri lalu
    retry tetap jalan sampai habis (search dipanggil max_retries+1 kali)."""
    mock_search.side_effect = Exception("timeout")  # TRANSIENT → on_retry jalan
    cb = CircuitBreaker(threshold=5, cooldown=10.0)
    fm = MagicMock()
    fm.decide.return_value = {
        "action": "abort", "next_backend": None, "next_proxy": None,
        "reason": "semua resource mati",
    }
    fm.healthy_backend.return_value = None

    seen = []
    execute = build_query_executor(
        {"backend": "duckduckgo"},
        _case(circuit_breaker=cb, fallback_manager=fm,
              retry_handler=RetryHandler(max_retries=5, base_delay=0.0)),
        on_query_done=lambda q, r, ok: seen.append((q, ok)),
    )
    results = execute("q1")

    assert results == []
    assert mock_search.call_count == 1   # berhenti setelah keputusan abort
    assert seen == [("q1", False)]


# ── Rotasi proxy: next_proxy harus benar-benar dipakai ────────────────────

@patch("core.batch_runner.search_dork")
def test_rotate_proxy_decision_applied_to_next_attempt(mock_search):
    """Regresi: current_proxy diambil lalu diabaikan; next_proxy hanya di-log."""
    p1, p2 = "http://p1.example:8000", "http://p2.example:8001"
    pm = ProxyManager(proxies=[p1, p2], cooldown_seconds=60, strict=False, max_failures=0)
    cb = CircuitBreaker(threshold=5, cooldown=10.0)
    fm = FallbackManager(
        backends=["duckduckgo", "startpage"], circuit_breaker=cb, proxy_manager=pm,
    )

    mock_search.side_effect = [
        Exception("proxy tunnel failed"),      # → PROXY_FAIL → rotasi ke p2
        [{"title": "ok", "href": "http://a.com", "body": ""}],
    ]

    execute = build_query_executor(
        {"backend": "duckduckgo", "proxy_manager": pm},
        _case(circuit_breaker=cb, fallback_manager=fm,
              retry_handler=RetryHandler(max_retries=2, base_delay=0.0)),
    )
    results = execute("q1")

    assert len(results) == 1
    assert mock_search.call_count == 2
    first = mock_search.call_args_list[0].kwargs
    second = mock_search.call_args_list[1].kwargs
    assert first["forced_proxy"] == p1       # percobaan awal: proxy terpilih
    assert second["forced_proxy"] == p2      # percobaan ulang: hasil rotasi


# ── raise_on_error & on_query_done ────────────────────────────────────────

@patch("core.batch_runner.search_dork")
def test_raise_on_error_propagates_for_single_query_path(mock_search):
    mock_search.side_effect = Exception("fatal bug")
    seen = []
    execute = build_query_executor(
        {"backend": "auto"},
        _case(),
        on_query_done=lambda q, r, ok: seen.append(ok),
        raise_on_error=True,
    )
    from core.scanner import SearchError
    with pytest.raises(SearchError):
        execute("q1")
    assert seen == [False]  # status 'failed' tetap dicatat sebelum raise


@patch("core.batch_runner.search_dork")
def test_executor_marks_success(mock_search):
    mock_search.return_value = [{"title": "ok", "href": "http://a.com", "body": ""}]
    seen = []
    execute = build_query_executor({}, _case(), on_query_done=lambda q, r, ok: seen.append(ok))
    assert execute("q1")
    assert seen == [True]


# ── Integrasi: mode single-query memakai modul case ───────────────────────

@patch("core.batch_runner.search_dork")
def test_cli_single_query_uses_case_modules(mock_search, tmp_path, monkeypatch):
    """Regresi: path single-query tidak pernah menyentuh modul case --resilient."""
    mock_search.return_value = [
        {"title": "ok", "href": "http://a.com", "body": "x" * 30},
    ]
    cb = MagicMock()
    cb.allow.return_value = True
    stats = MagicMock()

    monkeypatch.chdir(tmp_path)
    args = atdork.build_parser().parse_args([
        "-q", "site:example.com", "--db-path", str(tmp_path / "t.db"),
        "--resilient",
    ])
    with patch.object(atdork, "_setup_case_modules",
                      return_value=_case(circuit_breaker=cb, stats_collector=stats)):
        atdork.cli_mode(args)

    # Circuit breaker & stats collector dipakai oleh path single-query
    cb.record_success.assert_called()
    stats.record_backend.assert_called()
