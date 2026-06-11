#!/usr/bin/env python3
"""
Atdork - DuckDuckGo Based OSINT Tool
Author : alzzmarket
GitHub : github.com/amnottdevv/atdork
"""

import argparse
import sys
import logging
import os
import json
from rich.console import Console
from rich.prompt import Prompt

from core.scanner import search_dork
from core.batch_runner import load_queries_from_file, parse_query_string, run_batch
from core.multi_thread_runner import run_batch_multithread
from core.proxy_manager import create_proxy_manager
from lib.display import show_banner, display_results
from lib.storage import save_results

console = Console()


def build_parser():
    parser = argparse.ArgumentParser(
        prog="atdork",
        description="Atdork – DuckDuckGo metasearch OSINT tool for professionals.",
        epilog='Contoh: %(prog)s -q "site:gov filetype:pdf" -r 10 -o hasil.json',
    )
    # Mode
    parser.add_argument(
        "--interactive", action="store_true",
        help="Jalankan mode interaktif (tanya jawab)."
    )
    # Opsi utama
    parser.add_argument("-q", "--query", type=str, help="Kata kunci / dork.")
    parser.add_argument(
        "-r", "--max-results", type=int, default=20,
        help="Jumlah hasil maksimum (1-100, default 20)."
    )
    # Parameter pencarian
    parser.add_argument(
        "--region", type=str, default="us-en",
        help="Region pencarian, contoh us-en, uk-en, ru-ru. Default us-en."
    )
    parser.add_argument(
        "--safesearch", type=str, default="moderate", choices=["on", "moderate", "off"],
        help="Level SafeSearch: on, moderate, off (default moderate)."
    )
    parser.add_argument(
        "--timelimit", type=str, default=None, choices=["d", "w", "m", "y"],
        help="Batas waktu hasil: d (hari), w (minggu), m (bulan), y (tahun)."
    )
    parser.add_argument(
        "--backend", type=str, default="auto",
        help='Mesin pencari backend, contoh: auto, bing, google, duckduckgo, brave, mojeek, startpage, yandex, yahoo, wikipedia. Default auto.'
    )
    # Request tuning
    parser.add_argument(
        "--user-agent", type=str, default=None,
        help="Custom User-Agent string. Kosongkan untuk rotasi otomatis."
    )
    parser.add_argument(
        "--timeout", type=int, default=10,
        help="Timeout request dalam detik (default 10)."
    )
    parser.add_argument(
        "--retries", type=int, default=2,
        help="Jumlah percobaan ulang jika gagal (default 2)."
    )
    parser.add_argument(
        "--delay", type=float, default=0,
        help="Jeda antar request (detik) untuk throttle."
    )
    # Proxy
    parser.add_argument("--proxy", type=str, help="Proxy URL, pisahkan dengan koma jika lebih dari satu.")
    parser.add_argument("--proxy-file", type=str, help="File berisi daftar proxy (satu per baris).")
    parser.add_argument("--tor", action="store_true", help="Aktifkan fallback Tor SOCKS5 (127.0.0.1:9050).")
    parser.add_argument("--proxy-cooldown", type=int, default=60, help="Cooldown proxy gagal dalam detik (default 60).")
    parser.add_argument("--strict", action="store_true", help="Jangan fallback ke koneksi langsung jika semua proxy down.")
    parser.add_argument("--max-failures", type=int, default=3, help="Hapus proxy permanen setelah kegagalan berturut-turut sebanyak ini (0=tidak pernah).")
    # Multi-threading
    parser.add_argument(
        "--concurrency", type=int, default=1,
        help="Jumlah thread paralel untuk batch processing (default 1 = sekuensial)."
    )
    parser.add_argument(
        "--max-fallback-failures", type=int, default=3,
        help="Batas kegagalan berturut-turut sebelum fallback ke sekuensial (default 3)."
    )
    # Batch processing
    parser.add_argument(
        "--batch-file", type=str, default=None,
        help="File berisi daftar query (satu per baris) untuk batch processing."
    )
    parser.add_argument(
        "--batch-separator", type=str, default=";",
        help="Separator jika -q berisi banyak query (default ';')."
    )
    # Output
    parser.add_argument("-o", "--output", type=str, help="Simpan hasil ke file ini.")
    parser.add_argument("--output-dir", type=str, help="Folder penyimpanan otomatis.")
    parser.add_argument(
        "--format", type=str, choices=["txt", "json", "csv"], default="txt",
        help="Format file output (default txt)."
    )
    parser.add_argument(
        "--no-snippet", action="store_true",
        help="Sembunyikan cuplikan di layar."
    )
    # Lain
    parser.add_argument("--debug", action="store_true", help="Tampilkan log debug.")
    parser.add_argument("--version", action="version", version="%(prog)s 2.0")

    return parser


def interactive_mode():
    """Alur tanya jawab seperti skrip awal."""
    show_banner()
    query = Prompt.ask("[bold yellow]Masukkan keyword/dork[/bold yellow]").strip()
    if not query:
        console.print("[red]Query kosong. Keluar.[/red]")
        return

    max_res_str = Prompt.ask(
        "[bold yellow]Jumlah maksimal hasil[/bold yellow]", default="20"
    )
    try:
        max_results = int(max_res_str)
        if max_results < 1:
            max_results = 10
        elif max_results > 100:
            console.print("[yellow]Maksimal 100 hasil. Diset ke 100.[/yellow]")
            max_results = 100
    except ValueError:
        console.print("[yellow]Input tidak valid, pakai default 20[/yellow]")
        max_results = 20

    console.print("\n[bold cyan]🔍 Memulai pencarian...[/bold cyan]")
    try:
        results = search_dork(query, max_results=max_results)
    except Exception as e:
        console.print(f"[red]Gagal: {e}[/red]")
        return

    display_results(results, query)

    if results and Prompt.ask(
        "[yellow]Simpan hasil ke file? (y/n)[/yellow]",
        choices=["y", "n"], default="n"
    ) == "y":
        path = save_results(results, query, output_format="txt")
        console.print(f"[green]✅ Disimpan ke: {path}[/green]")


def cli_mode(args):
    """Mode command line, langsung dari argumen."""
    # Batasi max_results
    if args.max_results < 1:
        args.max_results = 10
    elif args.max_results > 100:
        console.print("[yellow]Warning: max-results capped at 100.[/yellow]")
        args.max_results = 100

    # --- Setup logging ---
    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
    else:
        logging.basicConfig(level=logging.WARNING)

    # --- Buat proxy manager jika ada sumber proxy ---
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
            if proxy_manager:
                console.print("[dim]Proxy manager diinisialisasi.[/dim]")
                if args.debug:
                    stats = proxy_manager.get_stats_summary()
                    console.print(f"[dim]Proxy aktif: {stats['active']}, banned: {stats['banned']}[/dim]")
        except ValueError as e:
            console.print(f"[red]Proxy manager error: {e}[/red]")
            sys.exit(1)

    # --- Deteksi mode batch ---
    queries = []
    if args.batch_file:
        try:
            queries = load_queries_from_file(args.batch_file)
        except Exception as e:
            console.print(f"[red]Gagal membaca file batch: {e}[/red]")
            sys.exit(1)
    elif args.query and args.batch_separator in args.query:
        queries = parse_query_string(args.query, args.batch_separator)

    if queries:
        if len(queries) == 0:
            console.print("[yellow]Tidak ada query yang valid.[/yellow]")
            return

        console.print(f"[bold cyan]Batch mode: {len(queries)} query[/bold cyan]")

        # Pilih runner berdasarkan concurrency
        if args.concurrency > 1:
            batch_results = run_batch_multithread(
                queries=queries,
                concurrency=args.concurrency,
                fallback_sequential=True,
                max_consecutive_failures=args.max_fallback_failures,
                max_results=args.max_results,
                timeout=args.timeout,
                retries=args.retries,
                delay=args.delay,
                proxy_manager=proxy_manager,
                region=args.region,
                safesearch=args.safesearch,
                timelimit=args.timelimit,
                backend=args.backend,
                user_agent=args.user_agent,
            )
        else:
            batch_results = run_batch(
                queries=queries,
                max_results=args.max_results,
                timeout=args.timeout,
                retries=args.retries,
                delay=args.delay,
                proxy_manager=proxy_manager,
                region=args.region,
                safesearch=args.safesearch,
                timelimit=args.timelimit,
                backend=args.backend,
                user_agent=args.user_agent,
            )

        # Ringkasan
        total_hits = sum(len(v) for v in batch_results.values())
        console.print(f"\n[green]Batch selesai. Total {total_hits} hasil dari {len(queries)} query.[/green]")

        # Tampilkan statistik proxy jika ada dan debug
        if proxy_manager and args.debug:
            stats = proxy_manager.get_stats_summary()
            console.print(f"[dim]Proxy stats: aktif={stats['active']}, banned={stats['banned']}, success={stats['total_success']}, fail={stats['total_failure']}[/dim]")

        # Simpan hasil batch
        if args.output or args.output_dir:
            if args.output:
                # Satu file JSON untuk semua hasil
                with open(args.output, "w", encoding="utf-8") as f:
                    json.dump(batch_results, f, indent=2, ensure_ascii=False)
                console.print(f"[green]✅ Hasil batch disimpan ke: {args.output}[/green]")
            elif args.output_dir:
                os.makedirs(args.output_dir, exist_ok=True)
                for q, res in batch_results.items():
                    # Sanitasi nama file dari query
                    safe_name = "".join(
                        c if c.isalnum() or c in " _-()" else "_" for c in q
                    )[:50]
                    fname = f"{safe_name}.{args.format}"
                    fpath = os.path.join(args.output_dir, fname)

                    if args.format == "json":
                        with open(fpath, "w", encoding="utf-8") as f:
                            json.dump(res, f, indent=2, ensure_ascii=False)
                    elif args.format == "csv":
                        import csv
                        with open(fpath, "w", newline="", encoding="utf-8") as f:
                            writer = csv.DictWriter(f, fieldnames=["title", "href", "body"])
                            writer.writeheader()
                            for row in res:
                                writer.writerow(row)
                    else:  # txt
                        with open(fpath, "w", encoding="utf-8") as f:
                            f.write(f"Query: {q}\n\n")
                            for i, r in enumerate(res, 1):
                                f.write(f"[{i}] {r.get('title','')}\n{r.get('href','')}\n{r.get('body','')}\n\n")
                console.print(f"[green]✅ Hasil batch disimpan di folder: {args.output_dir}[/green]")
        return

    # --- Mode single query (tanpa batch) ---
    if not args.query:
        console.print("[red]Error: Query wajib diisi untuk mode non-interaktif.[/red]")
        sys.exit(1)

    console.print(f"[bold cyan]🔍 Searching for:[/bold cyan] {args.query}")

    try:
        results = search_dork(
            query=args.query,
            max_results=args.max_results,
            timeout=args.timeout,
            retries=args.retries,
            delay=args.delay,
            proxy_manager=proxy_manager,
            region=args.region,
            safesearch=args.safesearch,
            timelimit=args.timelimit,
            backend=args.backend,
            user_agent=args.user_agent,
        )
    except Exception as e:
        console.print(f"[red]Search failed: {e}[/red]")
        sys.exit(1)

    display_results(results, args.query, no_snippet=args.no_snippet)

    # Statistik proxy (jika ada)
    if proxy_manager and args.debug:
        stats = proxy_manager.get_stats_summary()
        console.print(f"[dim]Proxy stats: {stats}[/dim]")

    # Simpan single output
    if args.output or args.output_dir:
        path = save_results(
            results,
            args.query,
            output_path=args.output,
            output_format=args.format,
            output_dir=args.output_dir,
        )
        console.print(f"[green]✅ Disimpan ke: {path}[/green]")


def main():
    parser = build_parser()
    args = parser.parse_args()

    # Jika --interactive atau tidak ada argumen yang menunjukkan mode non-interaktif
    if args.interactive or (not args.query and not args.batch_file and not args.output and not args.output_dir):
        interactive_mode()
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
