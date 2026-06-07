#!/usr/bin/env python3
"""
Dork Scanner - DuckDuckGo Based OSINT Tool
"""
"""
Kalau mau share ni github minimal tag dev la tae
"""

import sys
import time
from datetime import datetime
from ddgs import DDGS

# Rich untuk tampilan profesional
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.prompt import Prompt
    from rich import print as rprint
    RICH_OK = True
except ImportError:
    RICH_OK = False
    print("[!] Install rich: pip install rich")
    sys.exit(1)

# PyFiglet untuk banner
try:
    from pyfiglet import Figlet
    FIGLET_OK = True
except ImportError:
    FIGLET_OK = False
    print("[!] Install pyfiglet: pip install pyfiglet")
    sys.exit(1)

console = Console()

def banner():
    """ASCII Banner dengan pyfiglet"""
    f = Figlet(font='slant')
    banner_text = f.renderText('Dork Scanner')
    console.print(f"[bold green]{banner_text}[/bold green]")
    
    # Developed by line sesuai permintaan
    dev_line = Panel(
        "[bold cyan]Developed by alzzmarket[/bold cyan] | [blue]github.com/amnottdevv/dork-scanners[/blue]",
        border_style="yellow",
        padding=(0, 1)
    )
    console.print(dev_line)
    console.print("[dim]Ethical use only | DuckDuckGo API[/dim]\n")

def search_dork(query, max_results=30):
    """Eksekusi dork query ke DuckDuckGo"""
    try:
        ddgs = DDGS()
        results = list(ddgs.text(query, max_results=max_results))
        return results
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return []

def display_results(results, query):
    """Tampilkan hasil dalam bentuk tabel rapi"""
    if not results:
        console.print("[yellow]Tidak ada hasil ditemukan.[/yellow]")
        return
    
    table = Table(title=f"[bold cyan]Hasil untuk:[/bold cyan] {query[:60]}", 
                  border_style="green",
                  show_header=True,
                  header_style="bold magenta")
    table.add_column("No", style="dim", width=4)
    table.add_column("Title", style="yellow", width=50)
    table.add_column("URL", style="blue", width=60)
    table.add_column("Cuplikan", style="white", width=40)
    
    for idx, res in enumerate(results, 1):
        table.add_row(
            str(idx),
            res.get('title', 'N/A')[:47] + "...",
            res.get('href', 'N/A')[:57] + "...",
            res.get('body', 'N/A')[:37] + "..."
        )
    console.print(table)
    console.print(f"[green]Total: {len(results)} hasil[/green]")

def save_to_file(results, query):
    """Simpan hasil ke file dengan timestamp"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"dork_{timestamp}.txt"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"Dork Scanner Results\nQuery: {query}\nTime: {datetime.now()}\n\n")
        for i, res in enumerate(results, 1):
            f.write(f"[{i}] {res.get('title', 'N/A')}\n")
            f.write(f"URL: {res.get('href', 'N/A')}\n")
            f.write(f"Cuplikan: {res.get('body', 'N/A')}\n\n")
    console.print(f"[green]✓ Disimpan ke {filename}[/green]")

def main():
    banner()
    
    # Langsung minta input dork (to the point)
    query = Prompt.ask("[bold yellow]Masukkan keyword/dork[/bold yellow]")
    if not query.strip():
        console.print("[red]Query tidak boleh kosong![/red]")
        return
    
    # Jumlah hasil
    max_res = Prompt.ask("[bold yellow]Jumlah maksimal hasil[/bold yellow]", default="20")
    try:
        max_res = int(max_res)
        if max_res < 1:
            max_res = 10
    except:
        max_res = 20
    
    console.print("\n[bold cyan]▶ Scanning...[/bold cyan]")
    
    # Progress spinner
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), 
                  transient=True) as progress:
        progress.add_task(description="Mencari di DuckDuckGo...", total=None)
        results = search_dork(query, max_results=max_res)
    
    if results:
        display_results(results, query)
        # Tanya simpan
        save_choice = Prompt.ask("[yellow]Simpan hasil ke file? (y/n)[/yellow]", choices=["y", "n"], default="n")
        if save_choice.lower() == "y":
            save_to_file(results, query)
    else:
        console.print("[red]Tidak ada hasil. Coba dork lain.[/red]")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️ Dibatalkan user[/yellow]")
        sys.exit(0)
