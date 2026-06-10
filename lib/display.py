from rich.console import Console
from rich.panel import Panel
from pyfiglet import Figlet

console = Console()


def show_banner():
    f = Figlet(font="slant")
    banner = f.renderText("Atdork")
    console.print(f"[bold green]{banner}[/bold green]")
    info_panel = Panel(
        "[bold cyan]Developed by alzzmarket[/bold cyan] | "
        "[blue]github.com/amnottdevv/atdork[/blue]\n"
        "[dim]Ethical use only | DuckDuckGo API[/dim]",
        border_style="yellow",
        padding=(0, 1),
    )
    console.print(info_panel)
    console.print()


def display_results(results, query, highlight=True, no_snippet=False):
    if not results:
        console.print("[yellow]Tidak ada hasil ditemukan.[/yellow]")
        return

    console.print(f"\n[bold cyan]Hasil untuk:[/bold cyan] {query}\n")
    for idx, res in enumerate(results, 1):
        title = res.get("title", "Tidak ada judul").strip()
        url = res.get("href", "").strip()
        snippet = (res.get("body", "") or "").strip()

        if not no_snippet and len(snippet) > 200:
            snippet = snippet[:200] + "..."

        console.print(f"[bold yellow]{idx}.[/bold yellow] [green]{title}[/green]")
        console.print(f"   [blue]URL:[/blue] {url}")
        if not no_snippet and snippet:
            console.print(f"   [dim]Cuplikan:[/dim] {snippet}")
        console.print("   " + "-" * 50)

    console.print(f"\n[green]Total: {len(results)} hasil[/green]")