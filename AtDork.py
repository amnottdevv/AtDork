#!/usr/bin/env python3
"""
Atdork - Professional OSINT Tool
Author : alzzmarket
GitHub : github.com/amnottdevv/atdork
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
from core.multi_thread_runner import run_batch_multithread
from core.proxy_manager import create_proxy_manager
from core.filter_vuln import filter_vulnerable
from lib.display import show_banner, display_results
from lib.storage import save_results
from lib.validator import filter_results, get_filter_stats
from core.database import Database
from core.logger import setup_logging

console = Console()

# ASCII Art Banner (ditampilkan di awal)
def _show_ascii_banner():
    """Tampilkan ASCII art header."""
    f = Figlet(font='slant')
    banner = f.renderText('Atdork')
    console.print(f"[bold green]{banner}[/bold green]")
    console.print("[bold cyan]Professional OSINT Tool[/bold cyan]")
    console.print(f"[dim]v2.2 - {datetime.now().strftime('%Y-%m-%d %H:%M')}[/dim]")
    console.print()

def build_parser():
    parser = argparse.ArgumentParser(
        prog="atdork",
        description="Atdork – Professional DuckDuckGo metasearch OSINT tool.",
        epilog='Contoh: atdork -q "site:gov filetype:pdf" -r 10 -o hasil.json'
    )
    # Konfigurasi
    parser.add_argument("--config", type=str, help="Path to YAML config file (default: atdork.yaml).")
    parser.add_argument("--interactive", action="store_true", help="Jalankan mode interaktif (tanya jawab).")

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
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--max-fallback-failures", type=int, default=3)
    
    # Batch
    parser.add_argument("--batch-file", type=str)
    parser.add_argument("--batch-separator", type=str, default=";")
    
    # Output
    parser.add_argument("-o", "--output", type=str, help="Simpan hasil ke file.")
    parser.add_argument("--output-dir", type=str)
    parser.add_argument("--format", type=str, choices=["txt","json","csv"], default="txt")
    parser.add_argument("--no-snippet", action="store_true")
    
    # Validasi
    parser.add_argument("--no-validate", action="store_true")
    parser.add_argument("--strict-filter", action="store_true")
    
    # Filter kerentanan
    parser.add_argument("--filter-vuln", type=str, help="Filter platform (e.g., wordpress).")
    
    # Scanner tambahan
    parser.add_argument("--no-fallback-backends", action="store_true")
    parser.add_argument("--no-verify", action="store_true")
    
    # Logging
    parser.add_argument("--log-file", type=str, default="atdork.log", help="Path file log.")
    
    # Database
    parser.add_argument("--db-path", type=str, default="atdork.db", help="Path SQLite database.")
    parser.add_argument("--resume", action="store_true", help="Resume batch yang tertunda (dari database).")
    parser.add_argument("--history", action="store_true", help="Tampilkan riwayat pencarian.")
    parser.add_argument("--no-dedup", action="store_true", help="Nonaktifkan deduplikasi global.")
    parser.add_argument("--export-db", type=str, help="Export database ke file (format sesuai ekstensi: json/csv).")
    
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--version", action="version", version="%(prog)s 2.2")
    return parser

def interactive_mode(db: Database):
    """Alur interaktif seperti skrip awal, tapi dengan integrasi database."""
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

    # Simpan ke database
    if db:
        qid = db.add_query(query, "completed")
        db.add_results_batch(qid, results)

    display_results(results, query)

    if results and Prompt.ask("[yellow]Simpan hasil ke file? (y/n)[/yellow]", choices=["y","n"], default="n") == "y":
        path = save_results(results, query, output_format="txt")
        console.print(f"[green]✅ Disimpan ke: {path}[/green]")

def cli_mode(args):
    """Mode command line utama yang sudah terintegrasi penuh."""
    # Setup logging
    setup_logging(debug=args.debug, log_file=args.log_file)
    logger = logging.getLogger(__name__)
    
    # Tampilkan banner di awal
    _show_ascii_banner()

    # Validasi max_results
    args.max_results = max(1, min(100, args.max_results))

    # Database connection
    db = Database(args.db_path) if (args.resume or args.history or args.export_db or not args.no_dedup) else None
    
    # Handle --history
    if args.history and db:
        rows = db.get_all_queries()
        if not rows:
            console.print("[yellow]Belum ada riwayat pencarian.[/yellow]")
        else:
            console.print("[bold cyan]Riwayat Pencarian:[/bold cyan]")
            for qid, text, status in rows:
                console.print(f"  [green]#{qid}[/green] [{status}] {text[:80]}")
        db.close()
        return

    # Handle --export-db
    if args.export_db and db:
        out = args.export_db
        if out.endswith('.json'):
            db.export_to_json(out)
        else:
            db.export_to_csv(out)
        console.print(f"[green]✅ Database diekspor ke: {out}[/green]")
        db.close()
        return

    # Handle --resume
    if args.resume and db:
        pending = db.get_pending_queries()
        if not pending:
            console.print("[yellow]Tidak ada query yang tertunda.[/yellow]")
            db.close()
            return
        queries = [q[1] for q in pending]
        console.print(f"[bold cyan]Resume mode: {len(queries)} query tertunda[/bold cyan]")
    else:
        queries = []

    # Deteksi batch dari file/string
    if not queries:
        if args.batch_file:
            try:
                queries = load_queries_from_file(args.batch_file)
            except Exception as e:
                console.print(f"[red]Gagal membaca file batch: {e}[/red]")
                sys.exit(1)
        elif args.query and args.batch_separator in args.query:
            queries = parse_query_string(args.query, args.batch_separator)
        elif args.query:
            queries = [args.query]

    if not queries:
        console.print("[red]Error: Tidak ada query yang diberikan.[/red]")
        sys.exit(1)

    # Buat proxy manager jika perlu
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

    # Eksekusi batch atau single query
    if len(queries) > 1 or args.resume:
        # Mode batch
        console.print(f"[bold cyan]Batch mode: {len(queries)} query[/bold cyan]")
        if args.concurrency > 1:
            batch_results = run_batch_multithread(
                queries=queries,
                concurrency=args.concurrency,
                fallback_sequential=True,
                max_consecutive_failures=args.max_fallback_failures,
                **scanner_kwargs
            )
        else:
            batch_results = run_batch(queries=queries, **scanner_kwargs)

        # Filter spam
        if not args.no_validate:
            total_removed = 0
            for q in batch_results:
                old = len(batch_results[q])
                batch_results[q] = filter_results(batch_results[q], strict=args.strict_filter)
                total_removed += old - len(batch_results[q])
            if total_removed:
                console.print(f"[dim]Filter: {total_removed} hasil spam/invalid dihapus.[/dim]")

        # Filter vuln jika diminta
        if args.filter_vuln:
            total_vuln = 0
            for q in batch_results:
                vuln, _ = filter_vulnerable(batch_results[q], platform=args.filter_vuln)
                total_vuln += len(vuln)
                batch_results[q] = vuln
            console.print(f"[bold red]🔴 {total_vuln} hasil berpotensi rentan ({args.filter_vuln}).[/bold red]")

        # Simpan ke database
        if db:
            for q, results in batch_results.items():
                qid = db.add_query(q, "completed")
                db.add_results_batch(qid, results)

        # Ringkasan
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

    else:
        # Single query
        q = queries[0]
        console.print(f"[bold cyan]🔍 Searching for:[/bold cyan] {q}")
        try:
            results = search_dork(query=q, **scanner_kwargs)
        except SearchError as e:
            console.print(f"[red]Search failed: {e}[/red]")
            sys.exit(1)

        if not args.no_validate:
            original = len(results)
            results = filter_results(results, strict=args.strict_filter)
            stats = get_filter_stats(original, len(results))
            if stats["removed"]:
                console.print(f"[dim]Filter: {stats['removed']} hasil dihapus.[/dim]")

        if args.filter_vuln:
            vuln, safe = filter_vulnerable(results, platform=args.filter_vuln)
            console.print(f"[bold red]🔴 Rentan: {len(vuln)}[/bold red] | [green]🟢 Aman: {len(safe)}[/green]")
            results = vuln

        # Database insert
        if db and not args.no_dedup:
            # Deduplikasi global
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

        display_results(results, q, no_snippet=args.no_snippet)

        if args.output:
            save_results(results, q, output_path=args.output, output_format=args.format)
            console.print(f"[green]✅ Disimpan ke: {args.output}[/green]")
        elif args.output_dir:
            os.makedirs(args.output_dir, exist_ok=True)
            path = save_results(results, q, output_dir=args.output_dir, output_format=args.format)
            console.print(f"[green]✅ Disimpan ke: {path}[/green]")

    if db:
        db.close()

def main():
    parser = build_parser()
    args, remaining = parser.parse_known_args()
    config = load_config(args.config)
    parser.set_defaults(**config)
    args = parser.parse_args(remaining, namespace=args)

    # Setup logging awal (sebelum mode)
    setup_logging(debug=args.debug, log_file=args.log_file)
    logger = logging.getLogger(__name__)

    # Database sederhana untuk mode interaktif (jika tidak ada argumen khusus)
    if args.interactive or (not args.query and not args.batch_file and not args.resume and not args.history and not args.export_db):
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
