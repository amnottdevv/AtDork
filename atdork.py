#!/usr/bin/env python3
"""
Atdork - Professional OSINT Tool
Version : 1.3.9.4
Author  : alzzmarket
GitHub  : github.com/amnottdevv/atdork
"""

import argparse
import sys
import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from rich.console import Console
from rich.prompt import Prompt
from pyfiglet import Figlet

from core.config import load_config
from core.scanner import search_dork, SearchError
from core.batch_runner import load_queries_from_file, parse_query_string, run_batch
from core.proxy_manager import create_proxy_manager
from core.filter_vuln import filter_vulnerable
from core.template_dork import load_template_dorks, list_available_templates
from core.post_processor import PostProcessor, extract_urls, extract_vulnerable_urls
from lib.display import show_banner, display_results
from lib.storage import save_results
from lib.validator import filter_results, get_filter_stats
from core.database import Database
from core.logger import setup_logging

# GHDB Scraper (Exploit-DB Google Hacking Database)
from core.ghdb_scraper import run_ghdb_scraper

# Case modules
from core.case.circuit_breaker import CircuitBreaker
from core.case.ip_guard import IPGuard
from core.case.fallback_manager import FallbackManager
from core.case.retry_handler import RetryHandler
from core.case.adaptive_delay import AdaptiveDelay
from core.case.recovery_strategy import RecoveryStrategy
from core.case.stats import StatsCollector

# Cache Manager
from core.manage_cache import SearchCache

# Notification
from core.notification import send_batch_summary

console = Console()


def _show_ascii_banner():
    """Tampilkan ASCII art header."""
    f = Figlet(font='slant')
    banner = f.renderText('Atdork')
    console.print(f"[bold green]{banner}[/bold green]")
    console.print("[bold cyan]Professional OSINT Tool[/bold cyan]")
    console.print(f"[dim]v1.3.9.4 - {datetime.now().strftime('%Y-%m-%d %H:%M')}[/dim]")
    console.print()


def _apply_vulnerability_filter(results, filter_arg: str):
    """Wrapper untuk filter kerentanan dengan error handling."""
    try:
        return filter_vulnerable(results, filter_arg=filter_arg)
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="atdork",
        description="Atdork – Professional DuckDuckGo metasearch OSINT tool.",
        epilog='Contoh: atdork -q "site:gov filetype:pdf" -r 10 -o hasil.json'
    )
    # Konfigurasi
    parser.add_argument("--config", type=str, help="Path to YAML config file.")
    parser.add_argument("--interactive", action="store_true", help="Jalankan mode interaktif.")

    # Opsi utama
    parser.add_argument("-q", "--query", type=str, help="Kata kunci / dork.")
    parser.add_argument("-r", "--max-results", type=int, default=20, help="Jumlah hasil maksimum (1-100).")

    # Parameter pencarian
    parser.add_argument("--region", type=str, default="us-en", help="Region pencarian.")
    parser.add_argument("--safesearch", type=str, default="moderate", choices=["on","moderate","off"])
    parser.add_argument("--timelimit", type=str, default=None, choices=["d","w","m","y"])
    parser.add_argument("--backend", type=str, default="auto", help="Backend mesin pencari.")

    # Request tuning
    parser.add_argument("--user-agent", type=str, help="Custom User-Agent.")
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--delay", type=float, default=0)

    # Proxy
    parser.add_argument("--proxy", type=str, help="Proxy URL (comma-separated).")
    parser.add_argument("--proxy-file", type=str)
    parser.add_argument("--tor", action="store_true", help="Gunakan Tor SOCKS5.")
    parser.add_argument("--proxy-cooldown", type=int, default=60)
    parser.add_argument("--strict", action="store_true", help="Jangan fallback ke direct.")
    parser.add_argument("--max-failures", type=int, default=3)

    # Multi-threading
    parser.add_argument("--concurrency", type=int, default=1, help="Jumlah thread paralel untuk batch (1 = sekuensial).")

    # Batch
    parser.add_argument("--batch-file", type=str)
    parser.add_argument("--batch-separator", type=str, default=";")

    # Output
    parser.add_argument("-o", "--output", type=str, help="Simpan hasil ke file.")
    parser.add_argument("--output-dir", type=str)
    parser.add_argument("--format", type=str, choices=["txt","json","csv"], default="txt")
    parser.add_argument("--no-snippet", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true", help="Tampilkan hasil pencarian ke layar dalam mode batch.")

    # Validasi (legacy)
    parser.add_argument("--no-validate", action="store_true", help="Matikan semua filter validasi.")
    parser.add_argument("--strict-filter", action="store_true", help="Filter ketat (title≥5, desc≥10, spam on, url all).")

    # Validasi granular
    parser.add_argument("--validate-url", type=str, default="all",
                        choices=["only", "path", "params", "all", "false"],
                        help="Mode validasi URL.")
    parser.add_argument("--validate-title", type=str, default="5",
                        help="Panjang minimal judul (integer) atau 'false' untuk matikan.")
    parser.add_argument("--validate-desc", type=str, default="10",
                        help="Panjang minimal deskripsi (integer) atau 'false' untuk matikan.")
    parser.add_argument("--validate-spam", type=str, default="true",
                        choices=["true", "false"],
                        help="Aktifkan/matikan filter spam.")

    # Filter kerentanan
    parser.add_argument("--filter-vuln", type=str, help="Filter platform (e.g., wordpress).")

    # Scanner tambahan
    parser.add_argument("--no-fallback-backends", action="store_true")
    parser.add_argument("--no-verify", action="store_true")

    # Logging
    parser.add_argument("--log-file", type=str, default="atdork.log", help="Path file log.")

    # Database
    parser.add_argument("--db-path", type=str, default="atdork.db", help="Path SQLite database.")
    parser.add_argument("--resume", action="store_true", help="Resume batch yang tertunda.")
    parser.add_argument("--history", action="store_true", help="Tampilkan riwayat pencarian.")
    parser.add_argument("--no-dedup", action="store_true", help="Nonaktifkan deduplikasi global.")
    parser.add_argument("--export-db", type=str, help="Export database ke file (json/csv).")

    # Case modules (v1.3.5)
    parser.add_argument("--resilient", action="store_true", help="Aktifkan mode tahan banting (circuit breaker, fallback).")
    parser.add_argument("--adaptive-delay", action="store_true", help="Gunakan delay adaptif berdasarkan respons backend.")
    parser.add_argument("--ip-guard", action="store_true", help="Aktifkan deteksi kebocoran IP (wajib dengan --strict).")

    # Post-Processor (v1.3.6)
    parser.add_argument("--exec", type=str, help="Jalankan command untuk setiap URL hasil (gunakan {} untuk URL).")
    parser.add_argument("--exec-on-vuln", type=str, help="Jalankan command hanya pada URL rentan (wajib --filter-vuln).")
    parser.add_argument("--exec-parallel", type=int, default=1, help="Jumlah proses paralel untuk --exec.")
    parser.add_argument("--exec-timeout", type=int, default=30, help="Timeout per command dalam detik.")

    # Cache (v1.3.7)
    parser.add_argument("--cache", action="store_true", help="Aktifkan caching hasil pencarian.")
    parser.add_argument("--cache-db", type=str, default="atdork_cache.db", help="Path database cache.")
    parser.add_argument("--cache-ttl", type=int, default=24, help="TTL cache dalam jam (default: 24).")
    parser.add_argument("--cache-only", action="store_true", help="Hanya gunakan cache, jangan lakukan pencarian baru.")
    parser.add_argument("--clear-cache", action="store_true", help="Hapus semua cache sebelum memulai.")

    # Notifications (v1.3.9)
    parser.add_argument("--notify", type=str, help="Kirim notifikasi ke platform:webhook (discord:, slack:, telegram:).")
    parser.add_argument("--notify-if-vuln", action="store_true", help="Hanya kirim notifikasi jika ada hasil rentan.")

    # Template Dork
    parser.add_argument("--template", type=str, help="Nama template dork.")
    parser.add_argument("--target", type=str, help="Target domain untuk substitusi {target} di template.")
    parser.add_argument("--select", type=str, help="Pilih dork tertentu dari template (contoh: 1,3,5).")
    parser.add_argument("--list-templates", action="store_true", help="Tampilkan daftar template yang tersedia.")
    parser.add_argument("--template-path", type=str, help="Path ke folder template.")
    parser.add_argument("--preview", action="store_true", help="Pratinjau isi template tanpa menjalankannya.")

    # GHDB Scraper
    ghdb_group = parser.add_argument_group("GHDB Scraper")
    ghdb_group.add_argument(
        "--ghdb-scraper", action="store_true",
        help="Jalankan mode GHDB scraper (ambil dork dari Exploit-DB Google Hacking Database).",
    )
    ghdb_group.add_argument(
        "--ghdb-file", type=str, default=None,
        help="Simpan hasil dork GHDB ke file. Format auto-detect dari ekstensi (.json atau .txt).",
    )
    ghdb_group.add_argument(
        "--ghdb-categories", type=str, default=None,
        help="Filter kategori GHDB, pisahkan dengan koma. Bisa nama (partial match, mis. 'password') "
             "atau ID numerik (mis. '9,12').",
    )
    ghdb_group.add_argument(
        "--ghdb-years", type=str, default=None,
        help="Filter tahun publikasi dork GHDB. Contoh: '2024' atau '2020-2023,2024'.",
    )
    ghdb_group.add_argument(
        "--ghdb-r", type=int, default=None,
        help="Batasi jumlah total dork GHDB yang diambil/disimpan (setelah filter kategori/tahun).",
    )
    ghdb_group.add_argument(
        "--ghdb-list-categories", action="store_true",
        help="Tampilkan daftar kategori GHDB beserta jumlah dork per kategori, lalu keluar.",
    )

    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--version", action="version", version="%(prog)s 1.3.9.4")
    return parser


def _parse_validation_args(args) -> dict:
    """Parse validation arguments dengan safe type conversion."""
    if args.no_validate:
        return {"strict": False}
    if args.strict_filter:
        return {"strict": True}
    
    # FIX HIGH: Safe type conversion untuk validate_title dan validate_desc
    try:
        min_title = None if args.validate_title == "false" else int(args.validate_title)
    except (ValueError, TypeError):
        console.print("[yellow]⚠️ Warning: Invalid --validate-title value, using default (5)[/yellow]")
        min_title = 5
    
    try:
        min_desc = None if args.validate_desc == "false" else int(args.validate_desc)
    except (ValueError, TypeError):
        console.print("[yellow]⚠️ Warning: Invalid --validate-desc value, using default (10)[/yellow]")
        min_desc = 10
    
    check_spam = args.validate_spam == "true"
    url_mode = args.validate_url
    return {
        "strict": None,
        "min_title": min_title,
        "min_desc": min_desc,
        "check_spam": check_spam,
        "url_mode": url_mode,
    }


def _setup_case_modules(args, proxy_manager) -> dict:
    """Inisialisasi modul-modul case berdasarkan flag."""
    modules = {
        "circuit_breaker": None,
        "ip_guard": None,
        "fallback_manager": None,
        "retry_handler": None,
        "adaptive_delay": None,
        "recovery_strategy": None,
        "stats_collector": None,
    }

    if args.resilient:
        modules["circuit_breaker"] = CircuitBreaker(threshold=3, cooldown=120.0)
        modules["fallback_manager"] = FallbackManager(
            backends=["duckduckgo", "startpage", "yandex", "yahoo", "wikipedia"],
            circuit_breaker=modules["circuit_breaker"],
            proxy_manager=proxy_manager,
        )
        modules["retry_handler"] = RetryHandler(max_retries=args.retries, base_delay=2.0)
        modules["recovery_strategy"] = RecoveryStrategy(circuit_breaker=modules["circuit_breaker"])
        modules["stats_collector"] = StatsCollector()

    if args.adaptive_delay:
        modules["adaptive_delay"] = AdaptiveDelay(
            base_delay=1.0, max_delay=60.0, backoff_factor=2.0, recovery_factor=0.9
        )

    if args.ip_guard and args.strict:
        try:
            real_ip = IPGuard.get_public_ip()
            if real_ip:
                modules["ip_guard"] = IPGuard(real_ip, strict=True)
                if proxy_manager:
                    first_proxy = proxy_manager.get_proxy()
                    modules["ip_guard"].establish_baseline(first_proxy)
        except Exception as e:
            console.print(f"[yellow]⚠️ Gagal menginisialisasi IP Guard: {e}[/yellow]")

    return modules


def _setup_cache(args) -> Optional[SearchCache]:
    """Inisialisasi cache manager jika diminta."""
    if not (args.cache or args.clear_cache or args.cache_only):
        return None

    cache = SearchCache(
        db_path=args.cache_db,
        default_ttl_hours=args.cache_ttl,
        auto_cleanup=True,
    )

    if args.clear_cache:
        deleted = cache.clear_all()
        console.print(f"[dim]Cache cleared: {deleted} entries removed.[/dim]")

    if not args.cache and not args.cache_only:
        cache.close()
        return None

    return cache


def _build_cache_params(args) -> Dict[str, Any]:
    """Bangun parameter untuk key cache."""
    return {
        "region": args.region,
        "safesearch": args.safesearch,
        "timelimit": args.timelimit,
        "backend": args.backend,
        "max_results": args.max_results,
    }


def interactive_mode(db: Database):
    show_banner()
    query = Prompt.ask("[bold yellow]Masukkan keyword/dork[/bold yellow]").strip()
    if not query:
        console.print("[red]Query kosong. Keluar.[/red]")
        return

    max_res_str = Prompt.ask("[bold yellow]Jumlah maksimal hasil[/bold yellow]", default="20")
    try:
        max_results = int(max_res_str)
        max_results = max(1, min(100, max_results))
    except ValueError:
        max_results = 20

    console.print("\n[bold cyan]🔍 Memulai pencarian...[/bold cyan]")
    try:
        results = search_dork(query, max_results=max_results)
    except SearchError as e:
        console.print(f"[red]Gagal: {e}[/red]")
        return

    if results:
        original = len(results)
        results = filter_results(results)
        stats = get_filter_stats(original, len(results))
        if stats["removed"] > 0:
            console.print(f"[dim]Filter: {stats['removed']} hasil spam/invalid dihapus.[/dim]")

    if db:
        qid = db.add_query(query, "completed")
        db.add_results_batch(qid, results)

    display_results(results, query)

    if results and Prompt.ask("[yellow]Simpan hasil ke file? (y/n)[/yellow]", choices=["y","n"], default="n") == "y":
        path = save_results(results, query, output_format="txt")
        console.print(f"[green]✅ Disimpan ke: {path}[/green]")


def cli_mode(args):
    setup_logging(debug=args.debug, log_file=args.log_file)
    logger = logging.getLogger(__name__)

    _show_ascii_banner()

    args.max_results = max(1, min(100, args.max_results))

    # Database connection
    db = Database(args.db_path) if (args.resume or args.history or args.export_db or not args.no_dedup) else None

    # Handle --list-templates
    if args.list_templates:
        templates = list_available_templates(args.template_path or "wordlists/templates")
        if not templates:
            console.print("[yellow]Tidak ada template ditemukan.[/yellow]")
        else:
            console.print("[bold cyan]Template Dorks Tersedia:[/bold cyan]")
            for t in templates:
                console.print(f"  [green]{t['name']}[/green] - {t['description']}")
        if db: db.close()
        return

    # Handle --preview
    if args.preview and args.template:
        try:
            for tname in args.template.split(","):
                tname = tname.strip()
                if not tname:
                    continue
                dorks = load_template_dorks(tname, target=args.target, select=args.select, template_path=args.template_path)
                console.print(f"[bold cyan]Preview template '{tname}':[/bold cyan]")
                for i, d in enumerate(dorks, 1):
                    console.print(f"  {i}. {d}")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
        if db: db.close()
        return

    # Handle --history
    if args.history and db:
        rows = db.get_all_queries()
        if not rows:
            console.print("[yellow]Belum ada riwayat pencarian.[/yellow]")
        else:
            console.print("[bold cyan]Riwayat Pencarian:[/bold cyan]")
            for qid, text, status in rows:
                console.print(f"  [green]#{qid}[/green] [{status}] {text[:80]}")
        if db: db.close()
        return

    # Handle --export-db
    if args.export_db and db:
        out = args.export_db
        if out.endswith('.json'):
            db.export_to_json(out)
        else:
            db.export_to_csv(out)
        console.print(f"[green]✅ Database diekspor ke: {out}[/green]")
        if db: db.close()
        return

    # Handle --resume
    if args.resume and db:
        pending = db.get_pending_queries()
        if not pending:
            console.print("[yellow]Tidak ada query yang tertunda.[/yellow]")
            if db: db.close()
            return
        queries = [q[1] for q in pending]
        console.print(f"[bold cyan]Resume mode: {len(queries)} query tertunda[/bold cyan]")
    else:
        queries = []

    # Kumpulkan query
    if not queries:
        if args.template:
            for tname in args.template.split(","):
                tname = tname.strip()
                if not tname:
                    continue
                try:
                    template_dorks = load_template_dorks(tname, target=args.target, select=args.select, template_path=args.template_path)
                    queries.extend(template_dorks)
                except Exception as e:
                    console.print(f"[red]Error loading template '{tname}': {e}[/red]")
                    sys.exit(1)

        if args.query:
            if args.batch_separator in args.query:
                custom_queries = parse_query_string(args.query, args.batch_separator)
            else:
                custom_queries = [args.query]
            queries.extend(custom_queries)

        if args.batch_file:
            try:
                file_queries = load_queries_from_file(args.batch_file)
                queries.extend(file_queries)
            except Exception as e:
                console.print(f"[red]Gagal membaca file batch: {e}[/red]")
                sys.exit(1)

    if not queries:
        console.print("[red]Error: Tidak ada query yang diberikan. Gunakan -q, --template, atau --batch-file.[/red]")
        sys.exit(1)

    # Proxy manager
    proxy_manager = None
    if args.proxy or args.proxy_file or args.tor:
        try:
            proxy_manager = create_proxy_manager(
                proxy_arg=args.proxy, proxy_file=args.proxy_file, enable_tor=args.tor,
                cooldown=args.proxy_cooldown, strict=args.strict, max_failures=args.max_failures,
            )
            console.print("[dim]Proxy manager diinisialisasi.[/dim]")
        except ValueError as e:
            console.print(f"[red]Proxy manager error: {e}[/red]")
            sys.exit(1)

    # Setup case modules
    case_modules = _setup_case_modules(args, proxy_manager)

    # Setup cache
    cache = _setup_cache(args)
    cache_params = _build_cache_params(args) if cache else None

    # Parameter scanner
    scanner_kwargs = {
        "max_results": args.max_results, "timeout": args.timeout, "retries": args.retries,
        "delay": args.delay, "proxy_manager": proxy_manager, "region": args.region,
        "safesearch": args.safesearch, "timelimit": args.timelimit, "backend": args.backend,
        "user_agent": args.user_agent, "verify": not args.no_verify,
        "fallback_backends": not args.no_fallback_backends,
    }

    val_kwargs = _parse_validation_args(args)

    # Jalankan batch atau single query
    if len(queries) > 1 or args.resume:
        console.print(f"[bold cyan]Batch mode: {len(queries)} query[/bold cyan]")
        try:
            batch_results = run_batch(
                queries=queries,
                case_modules=case_modules,
                concurrency=args.concurrency,
                **scanner_kwargs
            )
        except Exception as e:
            console.print(f"[red]Batch error: {e}[/red]")
            if db: db.close()
            if cache: cache.close()
            return

        if args.verbose:
            for q, res in batch_results.items():
                console.print(f"\n[bold yellow]━━━ {q} ━━━[/bold yellow]")
                display_results(res, q, no_snippet=args.no_snippet)

        total_removed = 0
        for q in batch_results:
            old = len(batch_results[q])
            batch_results[q] = filter_results(batch_results[q], **val_kwargs)
            total_removed += old - len(batch_results[q])
        if total_removed:
            console.print(f"[dim]Filter: {total_removed} hasil dihapus.[/dim]")

        if args.filter_vuln:
            total_vuln = 0
            for q in batch_results:
                vuln, safe, _ = _apply_vulnerability_filter(batch_results[q], args.filter_vuln)
                total_vuln += len(vuln)
                batch_results[q] = vuln
            console.print(f"[bold red]🔴 {total_vuln} hasil berpotensi rentan ({args.filter_vuln}).[/bold red]")

        if db:
            for q, results in batch_results.items():
                qid = db.add_query(q, "completed")
                db.add_results_batch(qid, results)

        total_hits = sum(len(v) for v in batch_results.values())
        console.print(f"\n[green]Batch selesai. Total {total_hits} hasil.[/green]")

        # Post-processing: --exec (semua URL)
        if args.exec:
            all_urls = []
            for q, res in batch_results.items():
                all_urls.extend(extract_urls(res))
            if all_urls:
                processor = PostProcessor(
                    command=args.exec,
                    parallel=args.exec_parallel,
                    timeout=args.exec_timeout,
                )
                console.print(f"[bold cyan]🔧 Post-Processing {len(all_urls)} URLs...[/bold cyan]")
                processor.process(all_urls)
                console.print(f"[dim]{processor.summary()}[/dim]")

        # Post-processing: --exec-on-vuln (hanya URL rentan)
        if args.exec_on_vuln:
            if not args.filter_vuln:
                console.print(
                    "[red]Error: --exec-on-vuln requires --filter-vuln to be set.[/red]\n"
                    "[yellow]Example: --exec-on-vuln 'wpscan --url {}' --filter-vuln wordpress[/yellow]"
                )
                sys.exit(1)

            vuln_urls = []
            for q, res in batch_results.items():
                vuln_urls.extend(extract_vulnerable_urls(res, filter_arg=args.filter_vuln))
            if vuln_urls:
                processor = PostProcessor(
                    command=args.exec_on_vuln,
                    parallel=args.exec_parallel,
                    timeout=args.exec_timeout,
                )
                console.print(f"[bold red]🔴 Post-Processing {len(vuln_urls)} VULNERABLE URLs...[/bold red]")
                processor.process(vuln_urls)
                console.print(f"[dim]{processor.summary()}[/dim]")
            else:
                console.print("[yellow]No vulnerable URLs found for post-processing.[/yellow]")

        # Notifications (v1.3.9)
        if args.notify:
            vuln_only = args.notify_if_vuln
            if not vuln_only or (args.filter_vuln and total_hits > 0):
                send_batch_summary(
                    batch_results=batch_results,
                    target=args.notify,
                    vulnerable_only=vuln_only,
                    total_hits=total_hits,
                    query_count=len(queries),
                )

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(batch_results, f, indent=2, ensure_ascii=False)
            console.print(f"[green]✅ Disimpan ke: {args.output}[/green]")
        elif args.output_dir:
            os.makedirs(args.output_dir, exist_ok=True)
            for q, res in batch_results.items():
                safe_name = "".join(c if c.isalnum() or c in " _-()" else "_" for c in q)[:50]
                fname = f"{safe_name}.{args.format}"
                fpath = os.path.join(args.output_dir, fname)
                if args.format == "json":
                    with open(fpath, "w", encoding="utf-8") as f:
                        json.dump(res, f, indent=2, ensure_ascii=False)
                elif args.format == "csv":
                    import csv
                    with open(fpath, "w", newline="", encoding="utf-8") as f:
                        writer = csv.DictWriter(f, fieldnames=["title","href","body"])
                        writer.writeheader()
                        for row in res:
                            writer.writerow(row)
                else:
                    with open(fpath, "w", encoding="utf-8") as f:
                        f.write(f"Query: {q}\n\n")
                        for i, r in enumerate(res, 1):
                            f.write(f"[{i}] {r.get('title','')}\n{r.get('href','')}\n{r.get('body','')}\n\n")
            console.print(f"[green]✅ Batch disimpan di folder: {args.output_dir}[/green]")

        if case_modules.get("adaptive_delay"):
            console.print("\n[bold cyan]Rate Limiter Recommendations:[/bold cyan]")
            for backend, rec in case_modules["adaptive_delay"].all_recommendations().items():
                console.print(f"  [yellow]{backend}[/yellow]: {rec}")

    else:
        q = queries[0]
        console.print(f"[bold cyan]🔍 Searching for:[/bold cyan] {q}")

        backend_for_rate = scanner_kwargs.get("backend", "auto")
        if case_modules.get("adaptive_delay"):
            case_modules["adaptive_delay"].wait(backend_for_rate)

        try:
            if cache and not args.cache_only:
                results = cache.get_or_set(
                    q, backend_for_rate,
                    search_dork,
                    params=cache_params,
                    ttl_hours=args.cache_ttl,
                    query=q, **scanner_kwargs
                )
            elif cache and args.cache_only:
                results = cache.get(q, backend_for_rate, cache_params)
                if results is None:
                    console.print("[yellow]Cache MISS — dan --cache-only aktif. Tidak ada hasil.[/yellow]")
                    if db: db.close()
                    if cache: cache.close()
                    return
            else:
                results = search_dork(query=q, **scanner_kwargs)

            if case_modules.get("adaptive_delay"):
                case_modules["adaptive_delay"].report(backend_for_rate, 200, len(results) > 0)
        except Exception as e:
            if case_modules.get("adaptive_delay"):
                if "429" in str(e):
                    case_modules["adaptive_delay"].report(backend_for_rate, 429, False)
                else:
                    case_modules["adaptive_delay"].report(backend_for_rate, 500, False)
            console.print(f"[red]Search failed: {e}[/red]")
            sys.exit(1)

        display_results(results, q, no_snippet=args.no_snippet)

        original = len(results)
        results = filter_results(results, **val_kwargs)
        stats = get_filter_stats(original, len(results))
        if stats["removed"]:
            console.print(f"[dim]Filter: {stats['removed']} hasil dihapus.[/dim]")

        if args.filter_vuln:
            vuln, safe, _ = _apply_vulnerability_filter(results, args.filter_vuln)
            console.print(f"[bold red]🔴 Rentan: {len(vuln)}[/bold red] | [green]🟢 Aman: {len(safe)}[/green]")
            results = vuln

        if db and not args.no_dedup:
            original_len = len(results)
            unique_results = []
            for r in results:
                if not db.is_duplicate(r.get("href","")):
                    unique_results.append(r)
            console.print(f"[dim]Deduplikasi: {original_len - len(unique_results)} dihapus.[/dim]")
            results = unique_results
            qid = db.add_query(q, "completed")
            db.add_results_batch(qid, results)
        elif db:
            qid = db.add_query(q, "completed")
            db.add_results_batch(qid, results)

        # Post-processing: --exec (semua URL)
        if args.exec:
            urls = extract_urls(results)
            if urls:
                processor = PostProcessor(
                    command=args.exec,
                    parallel=args.exec_parallel,
                    timeout=args.exec_timeout,
                )
                console.print(f"[bold cyan]🔧 Post-Processing {len(urls)} URLs...[/bold cyan]")
                processor.process(urls)
                console.print(f"[dim]{processor.summary()}[/dim]")

        # Post-processing: --exec-on-vuln (hanya URL rentan)
        if args.exec_on_vuln:
            if not args.filter_vuln:
                console.print(
                    "[red]Error: --exec-on-vuln requires --filter-vuln to be set.[/red]\n"
                    "[yellow]Example: --exec-on-vuln 'wpscan --url {}' --filter-vuln wordpress[/yellow]"
                )
                sys.exit(1)

            vuln_urls = extract_vulnerable_urls(results, filter_arg=args.filter_vuln)
            if vuln_urls:
                processor = PostProcessor(
                    command=args.exec_on_vuln,
                    parallel=args.exec_parallel,
                    timeout=args.exec_timeout,
                )
                console.print(f"[bold red]🔴 Post-Processing {len(vuln_urls)} VULNERABLE URLs...[/bold red]")
                processor.process(vuln_urls)
                console.print(f"[dim]{processor.summary()}[/dim]")
            else:
                console.print("[yellow]No vulnerable URLs found for post-processing.[/yellow]")

        # Notifications for single query
        if args.notify and results:
            vuln_only = args.notify_if_vuln
            if not vuln_only or (args.filter_vuln and len(results) > 0):
                batch_summary = {q: results}
                send_batch_summary(
                    batch_results=batch_summary,
                    target=args.notify,
                    vulnerable_only=vuln_only,
                    total_hits=len(results),
                    query_count=1,
                )

        if args.output:
            save_results(results, q, output_path=args.output, output_format=args.format)
            console.print(f"[green]✅ Disimpan ke: {args.output}[/green]")
        elif args.output_dir:
            os.makedirs(args.output_dir, exist_ok=True)
            path = save_results(results, q, output_dir=args.output_dir, output_format=args.format)
            console.print(f"[green]✅ Disimpan ke: {path}[/green]")

        if case_modules.get("adaptive_delay"):
            console.print("\n[bold cyan]Rate Limiter Recommendations:[/bold cyan]")
            for backend, rec in case_modules["adaptive_delay"].all_recommendations().items():
                console.print(f"  [yellow]{backend}[/yellow]: {rec}")

    if db:
        db.close()
    if cache:
        cache.close()


def main():
    # 1. Parser minimal khusus untuk --config
    config_parser = argparse.ArgumentParser(add_help=False)
    config_parser.add_argument("--config", type=str, default=None)
    config_args, remaining = config_parser.parse_known_args()

    # 2. Muat konfigurasi dengan penanganan error
    raw_config = {}
    if config_args.config:
        try:
            loaded = load_config(config_args.config)
            if isinstance(loaded, dict):
                raw_config = loaded
            elif loaded is not None:
                console.print("[yellow]Warning: Config file tidak menghasilkan dictionary, menggunakan default.[/yellow]")
        except Exception as e:
            console.print(f"[red]Error loading config file: {e}[/red]")
            console.print("[yellow]Melanjutkan dengan nilai default...[/yellow]")

    # Normalisasi kunci: ganti tanda '-' menjadi '_' agar cocok dengan argparse dest
    config = {k.replace('-', '_'): v for k, v in raw_config.items()}

    # 3. Bangun parser penuh
    parser = build_parser()

    # 4. Hanya terapkan kunci yang valid (dikenali oleh parser)
    valid_dests = {action.dest for action in parser._actions if action.dest != 'help'}
    filtered_config = {k: v for k, v in config.items() if k in valid_dests}
    if len(filtered_config) < len(config):
        ignored = set(config.keys()) - set(filtered_config.keys())
        console.print(f"[dim]Kunci config tidak dikenal diabaikan: {', '.join(ignored)}[/dim]")

    parser.set_defaults(**filtered_config)

    # 5. Parse seluruh command line
    args = parser.parse_args(remaining)

    setup_logging(debug=args.debug, log_file=args.log_file)

    # --- GHDB Scraper mode ---
    # Mode ini berdiri sendiri: kalau dipakai, tidak masuk ke alur pencarian/interaktif biasa.
    if args.ghdb_scraper or args.ghdb_list_categories:
        success = run_ghdb_scraper(
            output_file=args.ghdb_file,
            categories=args.ghdb_categories,
            years=args.ghdb_years,
            max_results=args.ghdb_r,
            list_categories=args.ghdb_list_categories,
            console=console,
        )
        sys.exit(0 if success else 1)

    # FIX URGENT: Complete the incomplete if statement from line 756
    # Check if interactive mode or no action parameters provided
    should_interactive = (
        args.interactive or 
        (not args.query and not args.batch_file and not args.resume and 
         not args.history and not args.export_db and not args.template and 
         not args.list_templates and not args.preview)
    )
    
    if should_interactive:
        db = Database(args.db_path)
        interactive_mode(db)
        db.close()
    else:
        cli_mode(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️ Dibatalkan[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        sys.exit(1)
