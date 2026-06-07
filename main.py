#!/usr/bin/env python3
"""
Kalau mau share ni github minimal tag dev la tae
"""
"""
Dork Scanner - DuckDuckGo Based OSINT Tool
Author: alzzmarket
GitHub: github.com/amnottdevv/dork-scanners
"""

import sys
from datetime import datetime
from ddgs import DDGS
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt
from pyfiglet import Figlet

# ========== INISIALISASI ==========
console = Console()

# ========== BANNER ==========
def show_banner():
    f = Figlet(font='slant')
    banner = f.renderText('Dork Scanner')
    console.print(f"[bold green]{banner}[/bold green]")
    info_panel = Panel(
        "[bold cyan]Developed by alzzmarket[/bold cyan] | "
        "[blue]github.com/amnottdevv/dork-scanners[/blue]\n"
        "[dim]Ethical use only | DuckDuckGo API[/dim]",
        border_style="yellow",
        padding=(0, 1)
    )
    console.print(info_panel)
    console.print()

# ========== PENCARIAN ==========
def search_dork(query: str, max_results: int = 30) -> list:
    try:
        ddgs = DDGS()
        results = list(ddgs.text(query, max_results=max_results))
        return results
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return []

# ========== TAMPILAN HASIL (PLAIN, TANPA TABEL) ==========
def display_results_plain(results: list, query: str):
    if not results:
        console.print("[yellow]Tidak ada hasil ditemukan.[/yellow]")
        return

    console.print(f"\n[bold cyan]Hasil untuk:[/bold cyan] {query}\n")
    for idx, res in enumerate(results, 1):
        title = res.get('title', 'Tidak ada judul').strip()
        url = res.get('href', '').strip()
        snippet = (res.get('body', '') or '').strip()
        if len(snippet) > 200:
            snippet = snippet[:200] + "..."

        console.print(f"[bold yellow]{idx}.[/bold yellow] [green]{title}[/green]")
        console.print(f"   [blue]URL:[/blue] {url}")
        if snippet:
            console.print(f"   [dim]Cuplikan:[/dim] {snippet}")
        console.print("   " + "-" * 50)
    console.print(f"\n[green]Total: {len(results)} hasil[/green]")

# ========== SIMPAN KE FILE ==========
def save_to_file(results: list, query: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"dork_{timestamp}.txt"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"Dork Scanner Results\nQuery: {query}\nTimestamp: {datetime.now()}\nTotal: {len(results)}\n\n")
        for i, res in enumerate(results, 1):
            f.write(f"[{i}] TITLE: {res.get('title', 'N/A')}\n")
            f.write(f"    URL: {res.get('href', 'N/A')}\n")
            f.write(f"    SNIPPET: {res.get('body', 'N/A')}\n")
            f.write("-" * 80 + "\n")
    console.print(f"[green]✅ Disimpan ke: {filename}[/green]")
    return filename

# ========== MAIN ==========
def main():
    show_banner()
    query = Prompt.ask("[bold yellow]Masukkan keyword/dork[/bold yellow]").strip()
    if not query:
        console.print("[red]Query kosong. Keluar.[/red]")
        return

    max_res_str = Prompt.ask("[bold yellow]Jumlah maksimal hasil[/bold yellow]", default="20")
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
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        progress.add_task(description="Menghubungi DuckDuckGo...", total=None)
        results = search_dork(query, max_results=max_results)

    if not results:
        console.print("[red]Tidak ada hasil. Coba dork lain.[/red]")
        return

    display_results_plain(results, query)

    if Prompt.ask("[yellow]Simpan hasil ke file? (y/n)[/yellow]", choices=["y", "n"], default="n") == "y":
        save_to_file(results, query)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️ Dibatalkan[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
