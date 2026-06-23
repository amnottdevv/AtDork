#!/usr/bin/env python3
"""
Atdork - Professional OSINT Tool
Version : 1.3.3
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
from rich.progress import Progress, SpinnerColumn, TextColumn
from pyfiglet import Figlet

from core.config import load_config
from core.scanner import search_dork, SearchError
from core.batch_runner import load_queries_from_file, parse_query_string, run_batch
from core.proxy_manager import create_proxy_manager
from core.filter_vuln import filter_vulnerable
from core.template_dork import load_template_dorks, list_available_templates
from lib.display import show_banner, display_results
from lib.storage import save_results
from lib.validator import filter_results, get_filter_stats
from core.database import Database
from core.logger import setup_logging

# ── Resilience & Rate Limiter ──────────────────────────────────────────
from core.case.resilience import ResilienceHandler
from core.case.rate_limiter import RateLimiter

console = Console()


def _show_ascii_banner():
    """Tampilkan ASCII art header."""
    f = Figlet(font='slant')
    banner = f.renderText('Atdork')
    console.print(f"[bold green]{banner}[/bold green]")
    console.print("[bold cyan]Professional OSINT Tool[/bold cyan]")
    console.print(f"[dim]v1.3.3 - {datetime.now().strftime('%Y-%m-%d %H:%M')}[/dim]")
    console.print()


def _apply_vulnerability_filter(results, filter_arg: str):
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
    parser.add_argument("--max-fallback-failures", type=int, default=3, help="Batas kegagalan berturut-turut sebelum fallback ke sekuensial")

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

    # Validasi granular (v1.3.1)
    parser.add_argument("--validate-url", type=str, default="all",
                        choices=["only", "path", "params", "all", "false"],
                        help="Mode validasi URL: only (domain), path (domain+path), params (domain+params), all (lengkap), false (mati).")
    parser.add_argument("--validate-title", type=str, default="5",
                        help="Panjang minimal judul (integer) atau 'false' untuk matikan (default: 5).")
    parser.add_argument("--validate-desc", type=str, default="10",
                        help="Panjang minimal deskripsi (integer) atau 'false' untuk matikan (default: 10).")
    parser.add_argument("--validate-spam", type=str, default="true",
                        choices=["true", "false"],
                        help="Aktifkan/matikan filter spam (default: true).")

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

    # Resilience & Rate Limiter (v1.3)
    parser.add_argument("--resilient", action="store_true",
                        help="Aktifkan mode tahan banting (circuit breaker, backend fallback).")
    parser.add_argument("--adaptive-delay", action="store_true",
                        help="Gunakan delay adaptif berdasarkan respons backend.")

    # Template Dork (v1.3.2)
    parser.add_argument("--template", type=str, help="Nama template dork (tanpa ekstensi) atau path ke file YAML. Bisa multiple (pisahkan dengan koma).")
    parser.add_argument("--target", type=str, help="Target domain untuk substitusi {target} di template.")
    parser.add_argument("--select", type=str, help="Pilih dork tertentu dari template (contoh: 1,3,5).")
    parser.add_argument("--list-templates", action="store_true", help="Tampilkan daftar template yang tersedia.")
    parser.add_argument("--template-path", type=str, help="Path ke folder template (default: wordlists/templates/).")
    parser.add_argument("--preview", action="store_true", help="Pratinjau isi template tanpa menjalankannya.")

    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--version", action="version", version="%(prog)s 1.3.3")
    return parser


def _parse_validation_args(args) -> dict:
    """Konversi argumen validasi ke dictionary untuk filter_results."""
    if args.no_validate:
        return {"strict": False}
    if args.strict_filter:
        return {"strict": True}

    min_title = None if args.validate_title == "false" else int(args.validate_title)
    min_desc = None if args.validate_desc == "false" else int(args.validate_desc)
    check_spam = args.validate_spam == "true"
    url_mode = args.validate_url

    return {
        "strict": None,
        "min_title": min_title,
        "min_desc": min_desc,
        "check_spam": check_spam,
        "url_mode": url_mode,
    }


def _create_resilience_handler(args, proxy_manager=None) -> Optional[ResilienceHandler]:
    if not args.resilient:
        return None
    return ResilienceHandler(
        active=True,
        max_retries=args.retries,
        backoff_base=2.0,
        max_backoff=30.0,
        circuit_threshold=3,
        circuit_cooldown=120.0,
        proxy_manager=proxy_manager,
    )


def _create_rate_limiter(args) -> Optional[RateLimiter]:
    if not args.adaptive_delay:
        return None
    return RateLimiter(
        base_delay=1.0,
        max_delay=60.0,
        backoff_factor=2.0,
        recovery_factor=0.9,
        min_delay=0.1,
    )


def interactive_mode(db: Database):
    """Alur interaktif seperti skrip awal."""
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
    """Mode command line utama yang sudah terintegrasi penuh."""
    setup_logging(debug=args.debug, log_file=args.log_file)
    logger = logging.getLogger(__name__)

    _show_ascii_banner()

    # Validasi max_results
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
                dorks = load_template_dorks(
                    tname,
                    target=args.target,
                    select=args.select,
                    template_path=args.template_path
                )
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

    # Kumpulkan query dari berbagai sumber
    if not queries:
        # Template dork (dukung multiple dengan koma)
        if args.template:
            for tname in args.template.split(","):
                tname = tname.strip()
                if not tname:
                    continue
                try:
                    template_dorks = load_template_dorks(
                        tname,
                        target=args.target,
                        select=args.select,
                        template_path=args.template_path
                    )
                    queries.extend(template_dorks)
                except Exception as e:
                    console.print(f"[red]Error loading template '{tname}': {e}[/red]")
                    sys.exit(1)

        # Query dari -q (bisa digabung)
        if args.query:
            if args.batch_separator in args.query:
                custom_queries = parse_query_string(args.query, args.batch_separator)
            else:
                custom_queries = [args.query]
            queries.extend(custom_queries)

        # Batch file
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
                proxy_arg=args.proxy,
                proxy_file=args.proxy_file,
                enable_tor=args.tor,
                cooldown=args.proxy_cooldown,
                strict=args.strict,
                max_failures=args.max_failures,
            )
            console.print("[dim]Proxy manager diinisialisasi.[/dim]")
        except ValueError as e:
            console.print(f"[red]Proxy manager error: {e}[/red]")
            sys.exit(1)

    # Resilience & Rate limiter
    resilience_handler = _create_resilience_handler(args, proxy_manager)
    rate_limiter = _create_rate_limiter(args)

    # Parameter scanner yang akan diteruskan
    scanner_kwargs = {
        "max_results": args.max_results,
        "timeout": args.timeout,
        "retries": args.retries,
        "delay": args.delay,
        "proxy_manager": proxy_manager,
        "region": args.region,
        "safesearch": args.safesearch,
        "timelimit": args.timelimit,
        "backend": args.backend,
        "user_agent": args.user_agent,
        "verify": not args.no_verify,
        "fallback_backends": not args.no_fallback_backends,
    }

    # Parameter validasi
    val_kwargs = _parse_validation_args(args)

    # Jalankan batch atau single query
    if len(queries) > 1 or args.resume:
        console.print(f"[bold cyan]Batch mode: {len(queries)} query[/bold cyan]")
        batch_results = run_batch(
            queries=queries,
            resilience_handler=resilience_handler,
            rate_limiter=rate_limiter,
            concurrency=args.concurrency,
            **scanner_kwargs
        )

        # Tampilkan hasil jika --verbose
        if args.verbose:
            for q, res in batch_results.items():
                console.print(f"\n[bold yellow]━━━ {q} ━━━[/bold yellow]")
                display_results(res, q, no_snippet=args.no_snippet)

        # Filter validasi
        total_removed = 0
        for q in batch_results:
            old = len(batch_results[q])
            batch_results[q] = filter_results(batch_results[q], **val_kwargs)
            total_removed += old - len(batch_results[q])
        if total_removed:
            console.print(f"[dim]Filter: {total_removed} hasil dihapus.[/dim]")

        # Filter kerentanan (v1.3.3: gunakan parameter baru dan unpack 3 nilai)
        if args.filter_vuln:
            total_vuln = 0
            for q in batch_results:
                vuln, safe, _ = _apply_vulnerability_filter(batch_results[q], args.filter_vuln)
                total_vuln += len(vuln)
                batch_results[q] = vuln
            console.print(f"[bold red]🔴 {total_vuln} hasil berpotensi rentan ({args.filter_vuln}).[/bold red]")

        # Simpan ke database
        if db:
            for q, results in batch_results.items():
                qid = db.add_query(q, "completed")
                db.add_results_batch(qid, results)

        total_hits = sum(len(v) for v in batch_results.values())
        console.print(f"\n[green]Batch selesai. Total {total_hits} hasil.[/green]")

        # Output file
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

        # Rate limiter recommendations
        if rate_limiter:
            console.print("\n[bold cyan]Rate Limiter Recommendations:[/bold cyan]")
            for backend, rec in rate_limiter.all_recommendations().items():
                console.print(f"  [yellow]{backend}[/yellow]: {rec}")

    else:
        # ── Single query ──────────────────────────────────────────────
        q = queries[0]
        console.print(f"[bold cyan]🔍 Searching for:[/bold cyan] {q}")

        backend_for_rate = scanner_kwargs.get("backend", "auto")
        if rate_limiter:
            rate_limiter.wait(backend_for_rate)

        try:
            if resilience_handler:
                results, err = resilience_handler.execute(q, **scanner_kwargs)
                if err:
                    raise SearchError(err)
            else:
                results = search_dork(query=q, **scanner_kwargs)

            if rate_limiter:
                rate_limiter.report_response(backend_for_rate, 200, len(results) > 0)
        except Exception as e:
            if rate_limiter:
                if "429" in str(e):
                    rate_limiter.report_response(backend_for_rate, 429, False)
                else:
                    rate_limiter.report_response(backend_for_rate, 500, False)
            console.print(f"[red]Search failed: {e}[/red]")
            sys.exit(1)

        # Tampilkan hasil (single query selalu tampil)
        display_results(results, q, no_snippet=args.no_snippet)

        # Filter validasi
        original = len(results)
        results = filter_results(results, **val_kwargs)
        stats = get_filter_stats(original, len(results))
        if stats["removed"]:
            console.print(f"[dim]Filter: {stats['removed']} hasil dihapus.[/dim]")

        # Filter kerentanan (v1.3.3: gunakan parameter baru dan unpack 3 nilai)
        if args.filter_vuln:
            vuln, safe, _ = _apply_vulnerability_filter(results, args.filter_vuln)
            console.print(f"[bold red]🔴 Rentan: {len(vuln)}[/bold red] | [green]🟢 Aman: {len(safe)}[/green]")
            results = vuln

        # Database insert
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

        if args.output:
            save_results(results, q, output_path=args.output, output_format=args.format)
            console.print(f"[green]✅ Disimpan ke: {args.output}[/green]")
        elif args.output_dir:
            os.makedirs(args.output_dir, exist_ok=True)
            path = save_results(results, q, output_dir=args.output_dir, output_format=args.format)
            console.print(f"[green]✅ Disimpan ke: {path}[/green]")

        if rate_limiter:
            console.print("\n[bold cyan]Rate Limiter Recommendations:[/bold cyan]")
            for backend, rec in rate_limiter.all_recommendations().items():
                console.print(f"  [yellow]{backend}[/yellow]: {rec}")

    if db:
        db.close()


def main():
    parser = build_parser()
    args, remaining = parser.parse_known_args()
    config = load_config(args.config)
    parser.set_defaults(**config)
    args = parser.parse_args(remaining, namespace=args)

    setup_logging(debug=args.debug, log_file=args.log_file)

    if args.interactive or (not args.query and not args.batch_file and not args.resume and not args.history and not args.export_db and not args.template and not args.list_templates and not args.preview):
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
