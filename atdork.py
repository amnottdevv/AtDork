#!/usr/bin/env python3
"""
Atdork - Professional OSINT Tool
Version : 1.4.1
Author  : alzzmarket
GitHub  : github.com/amnottdevv/atdork

Changelog (1.4.1):
  - Plugin system: install extra Python tools from Atdork-DB and
    run them as `--<plugin>-<option>` flags on the main command.
      * Contract: a PLUGIN metadata literal (name/version/
        description/options) + a run(args, ctx) entry point.
      * atdork install @plugins/<tool> installs a tool folder;
        atdork plugins list|info|run inspects and launches them.
      * Metadata is parsed via ast.literal_eval (no code runs at
        listing/registration time); the module is imported only
        when one of its flags is actually triggered.
      * Trigger: the bare --<plugin> flag OR any --<plugin>-*
        argument; option dests are always <plugin>_<option>, so
        plugin flags can never collide with core flags.
      * ctx exposes console/workspace/package_dir/results_dir plus
        get_setting(), search(), and a guarded guard_write().
      * Package manager: VALID_EXTS += .py, nested tool folders
        (@plugins/<tool>/*.py), tool-folder refs install/uninstall
        every file in the folder, installed list shows plugins, and
        .py refs are rejected as dork content with a clear hint.
      * Config `plugins:` section (enabled/disabled/paths/options)
        with fail-fast validation.
  - Docs: new features/plugins.md, CLI reference section,
    troubleshooting entries #11/#12.

  - Workflow engine (fase 3): sequential multi-step dork campaigns
    defined in structured YAML under `workflows:` (any config layer)
    or standalone workflow.yaml files auto-discovered in the active
    environment root and the working directory.
      * atdork workflow list|validate|run, plus the one-shot flag
        atdork --run-workflow NAME ('.' = the single workflow found
        in the root) with --workflow-file/--workflow-target/
        --workflow-workers/--workflow-resume/--workflow-dry-run.
      * Steps run strictly in order; `when_results_below` triggers
        `retry_with` queries whose results merge + dedupe.
      * `workers: N` thread concurrency inside a step;
        `worker_overrides` overlays search kwargs per step (e.g.
        force the Serper API backend for one pool).
      * Resumable state per workflow
        (<env>/state/workflows/<name>.json): --resume skips steps
        already completed.
      * Step outputs (txt/json/csv) are written through the
        environment write guard; {target}/{step}/{date}/{run_id}
        substitution in queries and output paths.
  - Config loader: `workflows:` entries get a fail-fast structural
    check (mapping with a steps list) at load time.
  - Docs: new features/workflows.md, CLI reference section,
    examples/workflows/recon.yml + root workflow.yaml demo.

Changelog (1.4.0):
  - Professional YAML config v2: nested sections (search, engines,
    profiles, resilience, output), layered discovery
    (global ~/.config/atdork -> working dir -> --config), ${ENV}
    interpolation with ${VAR:-default} defaults, strict validation
    with clear errors. Legacy flat v1 files keep working unchanged.
  - Third-party search API providers (core/providers/): Serper.dev,
    SerpApi and Brave Search API, configured under `engines:` in
    atdork.yml. Results are normalised to {title, href, body};
    quota/rate-limit/auth errors are classified so quota and rate
    limits skip to the next backend without wasting retries, and API
    keys are masked everywhere via the redactor.
  - Named backend chains: `profiles:` entries usable as
    --backend <name>; `search.fallback` defines the explicit chain.
  - --resilient circuit breaker is now tunable via `resilience:`.
  - Docs: configuration.md rewritten (full .yml guide), new
    engines.md (supported providers), examples/atdork.yml.

Changelog (1.3.9.7):
  - Dork data moved out of the tool into the Atdork-DB repository
    (github.com/amnottdevv/Atdork-DB): 100+ files across themed @folders
    (exploit-db, ghdb, shodan, censys, cms, cloud, crypto, gaming, movie,
    onion, bug-bounty, lfi/rfi, and more) plus the Index.idn manifest.
    The distribution is code-only now (data is fetched via install).
  - New package manager: atdork install/uninstall/installed/search/
    update/index. Refs like '@cve/cve_1.txt', 'c@cve_1.txt' or '@cve'
    work with --batch-file, --database-dork and --list-database-dork.
  - All Database Dork features (introduced in 1.3.9.5) now work
    transparently with the package index, including subfolder
    navigation, comma combos, folder-wide loads, and random selection.

Changelog (1.3.9.6):
  - Bundled dork database expanded to 900K+ dorks across 89 files
    (Bug Bounty, CCTV, CMS, Carding, Cloud, Cryptocurrency, Gaming,
     GitHub, LFI/RFI, Misc, Movie, Onion, Search Engines, Shodan,
     Shopping, exploit-db categories)
  - All Database Dork features (introduced in 1.3.9.5) now work
    transparently with the expanded database, including subfolder
    navigation, comma combos, and random selection.

Changelog (1.3.9.5):
  - Integrated `core/database_dork.py` for loading dorks from the bundled
    GHDB database (database/*.txt).
  - New flags:
      --extract-database              Extract bundled database to ./database
      --extract-database-to PATH      Custom destination for extraction
      --database-dork-extract PATH    Shortcut for extract (v1.3.9.5+)
      --force                         Overwrite existing destination
      --list-database-dork            List available database dork files
      --database-dork SPEC            Load dorks from database file(s)
      --database-r N                  Randomly select N dorks
      --database-path PATH            Custom database root directory
      --database-preview              Preview loaded dorks without running
      --database-seed N               Optional RNG seed for --database-r
"""

import argparse
import sys
import os
import json
import logging
import random
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from rich.console import Console
from rich.markup import escape
from rich.prompt import Prompt
from rich.table import Table
from pyfiglet import Figlet

from core.config import load_config, get_setting, override_setting, ConfigError
from core.env import EnvError, guard_if_env, resolve_env
from core.scanner import search_dork, SearchError
from core.batch_runner import (
    load_queries_from_file,
    parse_query_string,
    run_batch,
    build_query_executor,
)
from core.proxy_manager import create_proxy_manager
from core.filter_vuln import filter_vulnerable
from core.template_dork import load_template_dorks, list_available_templates
from core.database_dork import (
    load_database_dorks,
    list_database_dorks,
    extract_database,
)
from core.package_manager import (
    DBRepoNotFound,
    IndexNotFound,
    PackageError,
    RefError,
    build_index as build_pkg_index,
    find_db_repo,
    install as install_packages,
    list_installed,
    load_index,
    read_index_header,
    resolve_batch_file,
    search as search_index,
    uninstall as uninstall_packages,
    update_repo,
)
from core.post_processor import PostProcessor, extract_urls, extract_vulnerable_urls
from lib.display import show_banner, display_results
from lib.storage import save_results
from lib.validator import filter_results, get_filter_stats
from core.database import (
    Database,
    STATUS_PENDING,
    STATUS_COMPLETED,
    STATUS_FAILED,
)
from core.logger import setup_logging

# GHDB Scraper (Exploit-DB Google Hacking Database)
from core.ghdb_scraper import run_ghdb_scraper

# Case modules
from core.case.circuit_breaker import CircuitBreaker
from core.case.ip_guard import IPGuard, IPGuardError
from core.case.fallback_manager import FallbackManager
from core.case.retry_handler import RetryHandler
from core.case.adaptive_delay import AdaptiveDelay
from core.case.recovery_strategy import RecoveryStrategy
from core.case.stats import StatsCollector

# Cache Manager
from core.manage_cache import SearchCache

# Notification
from core.notification import send_batch_summary

# Workflow engine (fase 3)
from core.workflow import (
    WORKFLOW_FILENAMES,
    WorkflowEngine,
    WorkflowError,
    collect_workflows,
    discover_workflow_files,
    load_workflow_file,
    validate_workflow,
)

# Plugin system (core/plugins.py)
from core.plugins import (
    PluginDef,
    PluginError,
    discover_plugins,
    dispatch_plugin,
    make_context,
    register_plugin_args,
    run_plugin,
)

VERSION = "1.4.1"

console = Console()
logger = logging.getLogger("atdork")


def _show_ascii_banner():
    """Tampilkan ASCII art header."""
    f = Figlet(font='slant')
    banner = f.renderText('Atdork')
    console.print(f"[bold green]{banner}[/bold green]")
    console.print("[bold cyan]Professional OSINT Tool[/bold cyan]")
    console.print(f"[dim]v{VERSION} - {datetime.now().strftime('%Y-%m-%d %H:%M')}[/dim]")
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
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Package commands (dork packages from Atdork-DB):\n"
            "  atdork install <ref>     Install a package (e.g. c@cve_1.txt or @cve)\n"
            "  atdork uninstall <ref>   Remove an installed package\n"
            "  atdork installed         List installed packages\n"
            "  atdork search <keyword>  Search the package index\n"
            "  atdork update            Pull the latest Atdork-DB data\n"
            "  atdork index --build     Rebuild Index.idn (repository maintainer)\n"
            "\n"
            "Package refs: @cve/cve_1.txt (canonical), c@cve_1.txt (shorthand),\n"
            "              @cve (whole folder)\n"
            "\n"
            'Example: atdork -q "site:gov filetype:pdf" -r 10 -o results.json'
        ),
    )
    # Konfigurasi
    parser.add_argument("--config", type=str, help="Path to YAML config file.")
    parser.add_argument("--env", type=str,
                        help="AtDork environment root (all results/cache/logs/state "
                             "stay inside it). Also: ATDORK_ENV, 'atdork env use'.")
    wf_group = parser.add_argument_group("workflow engine")
    wf_group.add_argument("--run-workflow", metavar="NAME", default=None,
                          help="Run a named workflow (config 'workflows:', a "
                               "workflow.yaml in the root, or --workflow-file). "
                               "'.' runs the single workflow discovered in the root.")
    wf_group.add_argument("--workflow-file", metavar="FILE", default=None,
                          help="Read workflow definitions from this YAML file.")
    wf_group.add_argument("--workflow-target", metavar="TARGET", default=None,
                          help="Override the workflow target ({target} substitution).")
    wf_group.add_argument("--workflow-workers", metavar="N", type=int, default=None,
                          help="Override the worker (thread) count for every step.")
    wf_group.add_argument("--workflow-resume", action="store_true",
                          help="Resume: skip steps already completed in the saved state.")
    wf_group.add_argument("--workflow-dry-run", action="store_true",
                          help="Print the resolved queries without searching.")
    parser.add_argument("--interactive", action="store_true", help="Run interactive mode.")

    # Package manager (Atdork-DB)
    pkg_group = parser.add_argument_group("package manager (Atdork-DB)")
    pkg_group.add_argument(
        "--db-repo", type=str,
        help="Path to the Atdork-DB checkout (default: auto-discover, or config key 'db_repo').",
    )
    pkg_group.add_argument(
        "--db-repo-url", type=str,
        help="Git URL of the Atdork-DB repository (default: GitHub amnottdevv/Atdork-DB).",
    )
    pkg_group.add_argument(
        "--package-dir", type=str,
        help="Local package store directory (default: ~/.atdork/packages).",
    )

    # Opsi utama
    parser.add_argument("-q", "--query", type=str, help="Keyword / dork.")
    parser.add_argument("-r", "--max-results", type=int, default=20, help="Maximum number of results (1-100).")

    # Parameter pencarian
    parser.add_argument("--region", type=str, default="us-en", help="Search region.")
    parser.add_argument("--safesearch", type=str, default="moderate", choices=["on","moderate","off"])
    parser.add_argument("--timelimit", type=str, default=None, choices=["d","w","m","y"])
    parser.add_argument("--backend", type=str, default="auto",
                        help="Search engine backend: auto, google, bing, duckduckgo, brave, "
                             "mojeek, startpage, wikipedia, ... — or an API engine configured "
                             "under engines: in atdork.yml (serper, serpapi, brave), or a "
                             "chain name from profiles:.")

    # Request tuning
    parser.add_argument("--user-agent", type=str, help="Custom User-Agent.")
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--delay", type=float, default=0)

    # Proxy
    parser.add_argument("--proxy", type=str, help="Proxy URL (comma-separated).")
    parser.add_argument("--proxy-file", type=str)
    parser.add_argument("--tor", action="store_true", help="Use Tor SOCKS5.")
    parser.add_argument("--proxy-cooldown", type=int, default=60)
    parser.add_argument("--strict", action="store_true", help="Do not fallback to direct.")
    parser.add_argument("--max-failures", type=int, default=3)

    # Multi-threading
    parser.add_argument("--concurrency", type=int, default=1, help="Number of parallel threads for batch (1 = sequential).")

    # Batch
    parser.add_argument("--batch-file", type=str)
    parser.add_argument("--batch-separator", type=str, default=";")

    # Output
    parser.add_argument("-o", "--output", type=str, help="Save results to file.")
    parser.add_argument("--output-dir", type=str)
    parser.add_argument("--format", type=str, choices=["txt","json","csv"], default="txt")
    parser.add_argument("--no-snippet", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true", help="Display search results on screen in batch mode.")

    # Validasi (legacy)
    parser.add_argument("--no-validate", action="store_true", help="Disable all validation filters.")
    parser.add_argument("--strict-filter", action="store_true", help="Strict filter (title≥5, desc≥10, spam on, url all).")

    # Validasi granular
    parser.add_argument("--validate-url", type=str, default="all",
                        choices=["only", "path", "params", "all", "false"],
                        help="URL validation mode.")
    parser.add_argument("--validate-title", type=str, default="5",
                        help="Minimum title length (integer) or 'false' to disable.")
    parser.add_argument("--validate-desc", type=str, default="10",
                        help="Minimum description length (integer) or 'false' to disable.")
    parser.add_argument("--validate-spam", type=str, default="true",
                        choices=["true", "false"],
                        help="Enable/disable spam filter.")

    # Filter kerentanan
    parser.add_argument("--filter-vuln", type=str, help="Filter platform (e.g., wordpress).")

    # Scanner tambahan
    parser.add_argument("--no-fallback-backends", action="store_true")
    parser.add_argument("--no-verify", action="store_true")

    # Logging
    parser.add_argument("--log-file", type=str, default="atdork.log", help="Log file path.")

    # Database (SQLite history/dedup)
    parser.add_argument("--db-path", type=str, default="atdork.db", help="Path SQLite database.")
    parser.add_argument("--resume", action="store_true", help="Resume pending batch queries.")
    parser.add_argument("--history", action="store_true", help="Show search history.")
    parser.add_argument("--no-dedup", action="store_true", help="Disable global deduplication.")
    parser.add_argument("--export-db", type=str, help="Export database to file (json/csv).")

    # Case modules (v1.3.5)
    parser.add_argument("--resilient", action="store_true", help="Enable resilient mode (circuit breaker, fallback).")
    parser.add_argument("--adaptive-delay", action="store_true", help="Use adaptive delay based on backend response.")
    parser.add_argument("--ip-guard", action="store_true", help="Detect IP leaks during search (requires --proxy/--proxy-file/--tor; use --strict to stop on leak).")

    # Post-Processor (v1.3.6)
    parser.add_argument("--exec", type=str, help="Run command for each result URL (use {} for the URL).")
    parser.add_argument("--exec-on-vuln", type=str, help="Run command only on vulnerable URLs (requires --filter-vuln).")
    parser.add_argument("--exec-parallel", type=int, default=1, help="Number of parallel processes for --exec.")
    parser.add_argument("--exec-timeout", type=int, default=30, help="Timeout per command in seconds.")

    # Cache (v1.3.7)
    parser.add_argument("--cache", action="store_true", help="Enable search result caching (applies to single & batch mode).")
    parser.add_argument("--cache-db", type=str, default="atdork_cache.db", help="Cache database path.")
    parser.add_argument("--cache-ttl", type=int, default=24, help="Cache TTL in hours (default: 24).")
    parser.add_argument("--cache-only", action="store_true", help="Use cache only, do not perform new searches.")
    parser.add_argument("--clear-cache", action="store_true", help="Clear all cache before starting.")

    # Notifications (v1.3.9)
    parser.add_argument("--notify", type=str, help="Send notifications to platform:webhook (discord:, slack:, telegram:).")
    parser.add_argument("--notify-if-vuln", action="store_true", help="Only send notifications if there are vulnerable results.")

    # Template Dork
    parser.add_argument("--template", type=str, help="Dork template name.")
    parser.add_argument("--target", type=str, help="Target domain for {target} substitution in templates.")
    parser.add_argument("--select", type=str, help="Select specific dorks from a template (e.g.: 1,3,5).")
    parser.add_argument("--list-templates", action="store_true", help="Show list of available templates.")
    parser.add_argument("--template-path", type=str, help="Path to the template folder.")
    parser.add_argument("--preview", action="store_true", help="Preview template contents without running it.")

    # Database Dork (v1.3.9.5) — NEW
    db_group = parser.add_argument_group(
        "Database Dork (Atdork-DB packages)",
        "Load dorks from the Atdork-DB repository (Index.idn). "
        "Refs: '@ghdb/01_footholds', 'c@cve_1.txt', whole folder '@ghdb', "
        "or bare names like '01_footholds'. Examples:\n"
        "  atdork --list-database-dork\n"
        "  atdork --database-dork @ghdb/01_footholds --database-r 10\n"
        "  atdork --database-dork @ghdb/01_footholds,03_sensitive_directories\n"
        "  atdork --database-dork @cve --database-preview\n"
        "  atdork --database-dork /db-1/1_none --database-path /custom/db "
        "(legacy local copy)",
    )
    db_group.add_argument(
        "--extract-database", action="store_true",
        help="Copy a legacy local ./database directory to a destination "
             "(dork data now lives in the Atdork-DB repository).",
    )
    db_group.add_argument(
        "--extract-database-to", type=str, default=None,
        help="Custom destination directory for --extract-database.",
    )
    db_group.add_argument(
        "--database-dork-extract", type=str, default=None,
        metavar="PATH",
        help="Shortcut: copy a legacy local database to PATH. "
             "Equivalent to '--extract-database --extract-database-to PATH'. "
             "Use with --force to overwrite. "
             "Example: atdork --database-dork-extract mydork/",
    )
    db_group.add_argument(
        "--force", action="store_true",
        help="Overwrite existing destination when extracting.",
    )
    db_group.add_argument(
        "--list-database-dork", action="store_true",
        help="List all available database dork files with their dork counts.",
    )
    db_group.add_argument(
        "--database-dork", type=str, default=None,
        help="Comma-separated list of database dork file specs. Each spec may "
             "omit the .txt extension and may include subdirectory paths "
             "(e.g. '01_footholds', '/db-1/1_none', 'subdir/file.txt').",
    )
    db_group.add_argument(
        "--database-r", type=int, default=None,
        help="Randomly select N dorks from the combined set (without replacement).",
    )
    db_group.add_argument(
        "--database-path", type=str, default=None,
        help="Custom database root directory (overrides auto-discovery).",
    )
    db_group.add_argument(
        "--database-preview", action="store_true",
        help="Preview loaded database dorks without running a search.",
    )
    db_group.add_argument(
        "--database-seed", type=int, default=None,
        help="Optional RNG seed for reproducible --database-r selection.",
    )

    # GHDB Scraper
    ghdb_group = parser.add_argument_group("GHDB Scraper")
    ghdb_group.add_argument(
        "--ghdb-scraper", action="store_true",
        help="Run GHDB scraper mode (fetch dorks from Exploit-DB Google Hacking Database).",
    )
    ghdb_group.add_argument(
        "--ghdb-file", type=str, default=None,
        help="Save GHDB dork results to a file. Format is auto-detected from the extension (.json or .txt).",
    )
    ghdb_group.add_argument(
        "--ghdb-categories", type=str, default=None,
        help="Filter GHDB categories, comma-separated. Accepts names (partial match, e.g. 'password') "
             "or numeric IDs (e.g. '9,12').",
    )
    ghdb_group.add_argument(
        "--ghdb-years", type=str, default=None,
        help="Filter GHDB dork publication years. Example: '2024' or '2020-2023,2024'.",
    )
    ghdb_group.add_argument(
        "--ghdb-r", type=int, default=None,
        help="Limit the total number of GHDB dorks fetched/saved (after category/year filters).",
    )
    ghdb_group.add_argument(
        "--ghdb-list-categories", action="store_true",
        help="Show GHDB categories with dork counts per category, then exit.",
    )

    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    # Plugin flags (--<plugin> and the mandatory --<plugin>-<option> format)
    # must come after every core flag so collisions can be detected.
    register_plugin_args(parser, warn=lambda msg: logger.warning("%s", msg))
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
        # Tunable via the `resilience:` section of atdork.yml (schema v2).
        resilience = get_setting("resilience")
        if not isinstance(resilience, dict):
            resilience = {}
        cb_cfg = resilience.get("circuit_breaker")
        if not isinstance(cb_cfg, dict):
            cb_cfg = {}
        try:
            cb_threshold = int(cb_cfg.get("failure_threshold", 3))
            cb_cooldown = float(resilience.get("cooldown", cb_cfg.get("reset_timeout", 120.0)))
        except (TypeError, ValueError):
            cb_threshold, cb_cooldown = 3, 120.0
        modules["circuit_breaker"] = CircuitBreaker(threshold=cb_threshold, cooldown=cb_cooldown)

        # Backend chain: `search.fallback` from atdork.yml when set, else the
        # legacy scraping set.
        legacy_backends = ["duckduckgo", "startpage", "yandex", "yahoo", "wikipedia"]
        search_cfg = get_setting("search")
        chain: list = []
        if isinstance(search_cfg, dict):
            raw_chain = search_cfg.get("fallback")
            if isinstance(raw_chain, str):
                chain = [b.strip() for b in raw_chain.split(",") if b.strip()]
            elif isinstance(raw_chain, list):
                chain = [str(b).strip() for b in raw_chain if str(b).strip()]
        modules["fallback_manager"] = FallbackManager(
            backends=chain or legacy_backends,
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

    if args.ip_guard:
        # Bug lama: --ip-guard hanya diproses bila --strict juga aktif, dan
        # hasilnya tidak pernah dipakai sama sekali (IPGuard.check() tidak
        # pernah dipanggil di alur mana pun). Sekarang guard dibuat selalu
        # (bila ada proxy) dan check() dipanggil via _verify_ip_guard().
        if not proxy_manager:
            console.print(
                "[yellow]⚠️ --ip-guard requires --proxy/--proxy-file/--tor "
                "to monitor leaks; skipped.[/yellow]"
            )
        else:
            try:
                real_ip = IPGuard.get_public_ip()
                if real_ip:
                    modules["ip_guard"] = IPGuard(real_ip, strict=args.strict)
                    first_proxy = proxy_manager.get_proxy()
                    if first_proxy:
                        modules["ip_guard"].establish_baseline(first_proxy)
                    else:
                        console.print(
                            "[yellow]⚠️ No healthy proxy for IP Guard baseline; "
                            "IP Guard disabled.[/yellow]"
                        )
                        modules["ip_guard"] = None
                else:
                    console.print(
                        "[yellow]⚠️ Unable to determine real IP (all IP-check "
                        "providers failed); IP Guard disabled.[/yellow]"
                    )
            except Exception as e:
                console.print(f"[yellow]⚠️ Failed to initialize IP Guard: {e}[/yellow]")

    return modules


def _verify_ip_guard(
    ip_guard,
    proxy_manager,
    stats_collector=None,
    phase: str = "pre-run",
) -> Tuple[bool, str]:
    """
    Jalankan pengecekan IP Guard (bug lama: check() tidak pernah dipanggil).

    Args:
        ip_guard: Instance IPGuard atau None.
        proxy_manager: ProxyManager yang akan dipakai untuk pengecekan.
        stats_collector: StatsCollector opsional (untuk mencatat leak ke statistik).
        phase: Label fase pengecekan (untuk pesan: pre-run / post-run).

    Returns:
        (ok_to_continue, panic_message). ``ok_to_continue`` False hanya bila
        ada bukti nyata kebocoran IP dan mode strict aktif.
    """
    if not ip_guard:
        return True, ""

    proxy = None
    if proxy_manager:
        try:
            proxy = proxy_manager.get_proxy()
        except Exception as e:
            logger.debug("IPGuard[%s]: failed to get proxy for check: %s", phase, e)
            proxy = None

    try:
        ok, panic, warnings = ip_guard.enforce(proxy)
    except Exception as e:
        console.print(f"[yellow]⚠️ IP Guard failed to run ({phase}): {e}[/yellow]")
        return True, ""

    if stats_collector:
        try:
            stats_collector.record_ip_guard(check=True, leak=not ok)
        except Exception as e:
            logger.debug("StatsCollector.record_ip_guard failed: %s", e)

    for w in warnings:
        console.print(f"[yellow]⚠️ IP Guard({phase}): {w}[/yellow]")

    return ok, (panic or "")


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


# --------------------------------------------------------------------------- #
# Database Dork handlers (v1.3.9.5)
# --------------------------------------------------------------------------- #

def _handle_extract_database(args) -> None:
    """Handle --extract-database: copy a legacy local ./database directory."""
    dest = args.extract_database_to
    try:
        result_path = extract_database(dest_dir=dest, overwrite=args.force)
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    except FileExistsError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("[yellow]Hint: pass --force to overwrite.[/yellow]")
        sys.exit(1)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    # Show summary
    files = list_database_dorks(result_path)
    total_dorks = sum(f["count"] for f in files)
    console.print(f"[green]✅ Database extracted to: {result_path}[/green]")
    console.print(f"[dim]{len(files)} files, {total_dorks} dorks total.[/dim]")

    # Optional: show table
    if files:
        table = Table(title="Extracted Files", show_lines=False)
        table.add_column("File", style="cyan", no_wrap=True)
        table.add_column("Dorks", justify="right", style="green")
        for f in files:
            table.add_row(f["relpath"], str(f["count"]))
        table.add_row("[bold]TOTAL[/bold]", f"[bold]{total_dorks}[/bold]")
        console.print(table)


def _handle_list_database_dork(args) -> None:
    """Handle --list-database-dork: show available database files."""
    try:
        files = list_database_dorks(args.database_path)
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    if not files:
        console.print("[yellow]No dork files found.[/yellow]")
        console.print(
            "[dim]Hint: check --database-path, or rebuild the Atdork-DB "
            "index with 'atdork index --build'.[/dim]"
        )
        return

    table = Table(
        title=f"AtDork Database Dorks ({len(files)} files)",
        show_lines=False,
        title_style="bold cyan",
    )
    table.add_column("#", style="dim", justify="right", width=4)
    table.add_column("Spec", style="cyan", no_wrap=True)
    table.add_column("Dorks", justify="right", style="green", width=8)
    table.add_column("Size", justify="right", style="yellow", width=10)

    total_dorks = 0
    for i, f in enumerate(files, 1):
        relpath = f["relpath"]
        # Show spec without .txt extension (so user can copy-paste)
        spec = relpath
        if spec.lower().endswith(".txt"):
            spec = spec[:-4]
        size_str = _format_size(f["size_bytes"])
        table.add_row(str(i), spec, str(f["count"]), size_str)
        total_dorks += f["count"]

    table.add_row("", "[bold]TOTAL[/bold]", f"[bold]{total_dorks}[/bold]", "")
    console.print(table)

    if files:
        first_spec = files[0]["relpath"]
        if first_spec.lower().endswith(".txt"):
            first_spec = first_spec[:-4]
        second_spec = ""
        if len(files) > 1:
            second_spec = files[1]["relpath"]
            if second_spec.lower().endswith(".txt"):
                second_spec = second_spec[:-4]
            second_spec = f",{second_spec}"
        
        console.print(
            "\n[bold cyan]Usage examples:[/bold cyan]\n"
            f"  [dim]atdork --database-dork {first_spec} --database-r 10[/dim]\n"
            f"  [dim]atdork --database-dork {first_spec}{second_spec}[/dim]\n"
            "  [dim]atdork --database-dork /subdir/file --database-preview[/dim]"
        )


def _format_size(size_bytes: int) -> str:
    """Format bytes as human-readable string."""
    if size_bytes <= 0:
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _handle_database_dork_preview(args) -> None:
    """Handle --database-dork with --database-preview: show dorks without running."""
    if not args.database_dork:
        console.print("[red]Error: --database-preview requires --database-dork.[/red]")
        sys.exit(1)

    try:
        dorks = load_database_dorks(
            spec=args.database_dork,
            db_path=args.database_path,
            random_count=args.database_r,
            seed=args.database_seed,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    # Show source info
    spec_parts = [s.strip() for s in args.database_dork.split(",") if s.strip()]
    console.print(f"[bold cyan]📂 Database dorks loaded:[/bold cyan] {len(dorks)}")
    console.print(f"[dim]From: {', '.join(spec_parts)}[/dim]")
    if args.database_r:
        console.print(f"[dim]Random selection: {args.database_r} dorks[/dim]")
    if args.database_seed is not None:
        console.print(f"[dim]RNG seed: {args.database_seed}[/dim]")
    console.print()

    for i, dork in enumerate(dorks, 1):
        console.print(f"  [green]{i:4d}.[/green] {dork}")

    console.print(f"\n[bold green]Total: {len(dorks)} dorks ready.[/bold green]")
    console.print(
        "[dim]Remove --database-preview to execute them as batch queries.[/dim]"
    )


def _collect_database_queries(args) -> List[str]:
    """
    Collect queries from --database-dork.

    Returns:
        List of dork query strings.
    """
    if not args.database_dork:
        return []

    try:
        dorks = load_database_dorks(
            spec=args.database_dork,
            db_path=args.database_path,
            random_count=args.database_r,
            seed=args.database_seed,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error loading database dorks: {e}[/red]")
        sys.exit(1)

    if not dorks:
        console.print("[yellow]⚠️  No dorks loaded from database.[/yellow]")
        return []

    # Show summary
    spec_parts = [s.strip() for s in args.database_dork.split(",") if s.strip()]
    console.print(f"[bold cyan]📂 Database dorks loaded:[/bold cyan] {len(dorks)} from {len(spec_parts)} file(s)")
    console.print(f"[dim]Files: {', '.join(spec_parts)}[/dim]")
    if args.database_r:
        console.print(f"[dim]Random selection (--database-r {args.database_r}): {len(dorks)} dorks[/dim]")
    if args.database_seed is not None:
        console.print(f"[dim]RNG seed: {args.database_seed}[/dim]")

    # Show preview (first 5)
    if len(dorks) <= 5:
        for i, d in enumerate(dorks, 1):
            console.print(f"[dim]  {i}. {d}[/dim]")
    else:
        for i, d in enumerate(dorks[:3], 1):
            console.print(f"[dim]  {i}. {d}[/dim]")
        console.print(f"[dim]  ... ({len(dorks) - 3} more)[/dim]")

    return dorks


# --------------------------------------------------------------------------- #
# Interactive mode
# --------------------------------------------------------------------------- #

def interactive_mode(db: Database):
    show_banner()
    query = Prompt.ask("[bold yellow]Enter keyword/dork[/bold yellow]").strip()
    if not query:
        console.print("[red]Empty query. Exiting.[/red]")
        return

    max_res_str = Prompt.ask("[bold yellow]Maximum number of results[/bold yellow]", default="20")
    try:
        max_results = int(max_res_str)
        max_results = max(1, min(100, max_results))
    except ValueError:
        max_results = 20

    console.print("\n[bold cyan]🔍 Starting search...[/bold cyan]")
    if db:
        db.add_query(query, STATUS_PENDING)
    try:
        results = search_dork(query, max_results=max_results)
    except SearchError as e:
        if db:
            db.add_query(query, STATUS_FAILED)
        console.print(f"[red]Failed: {e}[/red]")
        return

    if results:
        original = len(results)
        results = filter_results(results)
        stats = get_filter_stats(original, len(results))
        if stats["removed"] > 0:
            console.print(f"[dim]Filter: {stats['removed']} spam/invalid results removed.[/dim]")

    if db:
        qid = db.add_query(query, STATUS_COMPLETED)
        db.add_results_batch(qid, results)

    display_results(results, query)

    if results and Prompt.ask("[yellow]Save results to file? (y/n)[/yellow]", choices=["y","n"], default="n") == "y":
        path = save_results(results, query, output_format="txt")
        console.print(f"[green]✅ Saved to: {path}[/green]")


def cli_mode(args):
    setup_logging(debug=args.debug, log_file=args.log_file)
    logger = logging.getLogger(__name__)

    _show_ascii_banner()

    args.max_results = max(1, min(100, args.max_results))

    # Database connection (SQLite history/dedup)
    db = Database(args.db_path) if (args.resume or args.history or args.export_db or not args.no_dedup) else None

    # ----- Database Dork: Handle extraction triggers -----
    # Three equivalent ways to trigger extraction:
    #   1. --extract-database                          (extract to ./database)
    #   2. --extract-database --extract-database-to X  (extract to X)
    #   3. --database-dork-extract X                   (shortcut, extract to X)
    #   4. --extract-database-to X                     (implicit, extract to X)
    if args.database_dork_extract:
        # Shortcut form: --database-dork-extract PATH
        args.extract_database = True
        args.extract_database_to = args.database_dork_extract
    elif args.extract_database_to and not args.extract_database:
        # Implicit form: --extract-database-to PATH (without --extract-database)
        args.extract_database = True
    
    if args.extract_database:
        _handle_extract_database(args)
        if db: db.close()
        return

    # ----- Database Dork: --list-database-dork (early exit) -----
    if args.list_database_dork:
        _handle_list_database_dork(args)
        if db: db.close()
        return

    # ----- Database Dork: --database-dork --database-preview (early exit) -----
    if args.database_dork and args.database_preview:
        _handle_database_dork_preview(args)
        if db: db.close()
        return

    # Handle --list-templates
    if args.list_templates:
        templates = list_available_templates(args.template_path or "wordlists/templates")
        if not templates:
            console.print("[yellow]No templates found.[/yellow]")
        else:
            console.print("[bold cyan]Available Dork Templates:[/bold cyan]")
            for t in templates:
                console.print(f"  [green]{t['name']}[/green] - {t['description']}")
        if db: db.close()
        return

    # Handle --preview (template)
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
            console.print("[yellow]No search history yet.[/yellow]")
        else:
            console.print("[bold cyan]Search History:[/bold cyan]")
            for qid, text, status in rows:
                # '\[' agar Rich tidak menelan status sebagai markup tag
                # (dahulu "[completed]" hilang dari layar tanpa disadari).
                console.print(f"  [green]#{qid}[/green] \\[{status}] {text[:80]}")
        if db: db.close()
        return

    # Handle --export-db
    if args.export_db and db:
        out = args.export_db
        if out.endswith('.json'):
            db.export_to_json(out)
        else:
            db.export_to_csv(out)
        console.print(f"[green]✅ Database exported to: {out}[/green]")
        if db: db.close()
        return

    # Handle --resume
    if args.resume and db:
        pending = db.get_pending_queries()
        if not pending:
            console.print("[yellow]No pending queries.[/yellow]")
            if db: db.close()
            return
        queries = [q[1] for q in pending]
        console.print(f"[bold cyan]Resume mode: {len(queries)} pending queries[/bold cyan]")
    else:
        queries = []

    # Kumpulkan query dari berbagai sumber
    if not queries:
        # 1. Template dorks
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

        # 2. Database dorks (NEW v1.3.9.5)
        if args.database_dork:
            db_queries = _collect_database_queries(args)
            queries.extend(db_queries)

        # 3. Single query (-q)
        if args.query:
            if args.batch_separator in args.query:
                custom_queries = parse_query_string(args.query, args.batch_separator)
            else:
                custom_queries = [args.query]
            queries.extend(custom_queries)

        # 4. Batch file (local path or package ref like @cve/cve_1.txt / c@cve_1.txt)
        if args.batch_file:
            try:
                batch_path = resolve_batch_file(args.batch_file)
                file_queries = load_queries_from_file(str(batch_path))
                queries.extend(file_queries)
            except PackageError as e:
                _print_ref_error(e)
                sys.exit(1)
            except Exception as e:
                console.print(f"[red]Failed to read batch file: {e}[/red]")
                sys.exit(1)

    if not queries:
        console.print("[red]Error: No query provided. Use -q, --template, --database-dork, or --batch-file.[/red]")
        sys.exit(1)

    # Proxy manager
    proxy_manager = None
    if args.proxy or args.proxy_file or args.tor:
        try:
            proxy_manager = create_proxy_manager(
                proxy_arg=args.proxy, proxy_file=args.proxy_file, enable_tor=args.tor,
                cooldown=args.proxy_cooldown, strict=args.strict, max_failures=args.max_failures,
            )
            console.print("[dim]Proxy manager initialized.[/dim]")
        except ValueError as e:
            console.print(f"[red]Proxy manager error: {e}[/red]")
            sys.exit(1)

    # Setup case modules
    case_modules = _setup_case_modules(args, proxy_manager)

    # Setup cache
    cache = _setup_cache(args)
    cache_params = _build_cache_params(args) if cache else None

    # IP Guard: pengecekan SEBELUM pencarian (bug lama: check() tidak pernah
    # dipanggil sama sekali — --ip-guard hanya jadi pajangan).
    ok, panic = _verify_ip_guard(
        case_modules.get("ip_guard"), proxy_manager,
        case_modules.get("stats_collector"), phase="pre-run",
    )
    if not ok:
        if db: db.close()
        if cache: cache.close()
        console.print(panic)
        sys.exit(3)

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

        # Tandai SEMUA query sebagai 'pending' sebelum dieksekusi (bug lama:
        # status tak pernah 'pending' sehingga --resume tidak pernah menemukan
        # apa pun). Kalau proses mati di tengah, baris ini yang disimpan.
        if db:
            for pending_q in dict.fromkeys(queries):
                db.add_query(pending_q, STATUS_PENDING)

        # Pelacak status per query (dipanggil dari thread batch → dikunci).
        success_map: Dict[str, bool] = {}
        success_lock = threading.Lock()

        def _on_query_done(query, results, success):
            with success_lock:
                success_map[query] = success

        try:
            batch_results = run_batch(
                queries=queries,
                case_modules=case_modules,
                concurrency=args.concurrency,
                cache=cache,
                cache_params=cache_params,
                cache_ttl=args.cache_ttl,
                cache_only=args.cache_only,
                on_query_done=_on_query_done,
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
            console.print(f"[dim]Filter: {total_removed} results removed.[/dim]")

        if args.filter_vuln:
            total_vuln = 0
            for q in batch_results:
                vuln, safe, _ = _apply_vulnerability_filter(batch_results[q], args.filter_vuln)
                total_vuln += len(vuln)
                batch_results[q] = vuln
            console.print(f"[bold red]🔴 {total_vuln} potentially vulnerable results ({args.filter_vuln}).[/bold red]")

        if db:
            for q, results in batch_results.items():
                # Query gagal (exception) → 'failed' agar diulang oleh --resume;
                # query sukses (termasuk yang 0 hasil) → 'completed' + simpan hasil.
                succeeded = success_map.get(q, bool(results))
                if args.cache_only and succeeded and not results:
                    # MISS di --cache-only: tidak ada yang benar-benar diambil,
                    # biarkan 'pending' supaya bisa diisi oleh --resume nanti
                    # (tanpa --cache-only).
                    continue
                qid = db.add_query(q, STATUS_COMPLETED if succeeded else STATUS_FAILED)
                if succeeded:
                    db.add_results_batch(qid, results)

        total_hits = sum(len(v) for v in batch_results.values())
        console.print(f"\n[green]Batch finished. Total {total_hits} results.[/green]")

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
            # Hormati --format: ekstensi .json/.csv dipakai bila cocok, selain
            # itu ikuti --format (bug lama: -o di mode batch SELALU JSON).
            ext = os.path.splitext(args.output)[1].lower()
            fmt = {".json": "json", ".csv": "csv"}.get(ext, args.format)
            if fmt == "csv":
                import csv
                with open(args.output, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=["query", "title", "href", "body"])
                    writer.writeheader()
                    for q, res in batch_results.items():
                        for row in res:
                            writer.writerow({
                                "query": q,
                                "title": row.get("title", ""),
                                "href": row.get("href", ""),
                                "body": row.get("body", ""),
                            })
            elif fmt == "txt":
                with open(args.output, "w", encoding="utf-8") as f:
                    for q, res in batch_results.items():
                        f.write(f"Query: {q}\n\n")
                        for i, r in enumerate(res, 1):
                            f.write(f"[{i}] {r.get('title','')}\n{r.get('href','')}\n{r.get('body','')}\n\n")
            else:
                with open(args.output, "w", encoding="utf-8") as f:
                    json.dump(batch_results, f, indent=2, ensure_ascii=False)
            console.print(f"[green]✅ Saved to: {args.output}[/green]")
        elif args.output_dir:
            os.makedirs(args.output_dir, exist_ok=True)
            used_names: Dict[str, int] = {}
            for q, res in batch_results.items():
                safe_name = "".join(c if c.isalnum() or c in " _-()" else "_" for c in q)[:50]
                # Nama unik: dua query yang hanya beda setelah karakter ke-50
                # tidak boleh saling menimpa file-nya.
                seen = used_names.get(safe_name, 0) + 1
                used_names[safe_name] = seen
                base = safe_name if seen == 1 else f"{safe_name}_{seen}"
                fname = f"{base}.{args.format}"
                fpath = os.path.join(args.output_dir, fname)
                while os.path.exists(fpath):
                    seen += 1
                    used_names[safe_name] = seen
                    fname = f"{safe_name}_{seen}.{args.format}"
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
                            # Tulis hanya kolom yang dikenal; result dict bisa
                            # punya key ekstra (mis. metadata provider) yang
                            # membuat DictWriter default (extrasaction='raise')
                            # melempar ValueError.
                            writer.writerow({
                                "title": row.get("title", ""),
                                "href": row.get("href", ""),
                                "body": row.get("body", ""),
                            })
                else:
                    with open(fpath, "w", encoding="utf-8") as f:
                        f.write(f"Query: {q}\n\n")
                        for i, r in enumerate(res, 1):
                            f.write(f"[{i}] {r.get('title','')}\n{r.get('href','')}\n{r.get('body','')}\n\n")
            console.print(f"[green]✅ Batch saved to folder: {args.output_dir}[/green]")

        if case_modules.get("adaptive_delay"):
            console.print("\n[bold cyan]Rate Limiter Recommendations:[/bold cyan]")
            for backend, rec in case_modules["adaptive_delay"].all_recommendations().items():
                console.print(f"  [yellow]{backend}[/yellow]: {rec}")

    else:
        q = queries[0]
        console.print(f"[bold cyan]🔍 Searching for:[/bold cyan] {q}")

        if db:
            db.add_query(q, STATUS_PENDING)

        def _record_status(query, results, success):
            """Tandai status query tunggal segera setelah eksekusi selesai."""
            if not db:
                return
            if success and not results and args.cache_only:
                # MISS di --cache-only → biarkan 'pending', belum ada yang
                # benar-benar diambil (bukan 'completed', bukan 'failed').
                return
            db.add_query(query, STATUS_COMPLETED if success else STATUS_FAILED)

        # Satu executor yang sama dengan mode batch: cache, resilient
        # (circuit breaker/fallback/retry), adaptive delay, dan status --resume
        # semuanya ikut terpakai di mode single-query (bug lama: path ini
        # sendiri-sendiri, cache-nya crash, dan modul case diabaikan).
        executor = build_query_executor(
            scanner_kwargs,
            case_modules,
            cache=cache,
            cache_params=cache_params,
            cache_ttl=args.cache_ttl,
            cache_only=args.cache_only,
            on_query_done=_record_status,
            raise_on_error=True,
        )

        try:
            results = executor(q)
        except Exception as e:
            console.print(f"[red]Search failed: {e}[/red]")
            if db: db.close()
            if cache: cache.close()
            sys.exit(1)

        if args.cache_only and not results:
            console.print("[yellow]Cache MISS — and --cache-only is enabled. No results.[/yellow]")
            if db: db.close()
            if cache: cache.close()
            return

        display_results(results, q, no_snippet=args.no_snippet)

        original = len(results)
        results = filter_results(results, **val_kwargs)
        stats = get_filter_stats(original, len(results))
        if stats["removed"]:
            console.print(f"[dim]Filter: {stats['removed']} results removed.[/dim]")

        if args.filter_vuln:
            vuln, safe, _ = _apply_vulnerability_filter(results, args.filter_vuln)
            console.print(f"[bold red]🔴 Vulnerable: {len(vuln)}[/bold red] | [green]🟢 Safe: {len(safe)}[/green]")
            results = vuln

        if db and not args.no_dedup:
            original_len = len(results)
            unique_results = []
            for r in results:
                if not db.is_duplicate(r.get("href","")):
                    unique_results.append(r)
            console.print(f"[dim]Deduplication: {original_len - len(unique_results)} removed.[/dim]")
            results = unique_results
            qid = db.add_query(q, STATUS_COMPLETED)
            db.add_results_batch(qid, results)
        elif db:
            qid = db.add_query(q, STATUS_COMPLETED)
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
            console.print(f"[green]✅ Saved to: {args.output}[/green]")
        elif args.output_dir:
            os.makedirs(args.output_dir, exist_ok=True)
            path = save_results(results, q, output_dir=args.output_dir, output_format=args.format)
            console.print(f"[green]✅ Saved to: {path}[/green]")

        if case_modules.get("adaptive_delay"):
            console.print("\n[bold cyan]Rate Limiter Recommendations:[/bold cyan]")
            for backend, rec in case_modules["adaptive_delay"].all_recommendations().items():
                console.print(f"  [yellow]{backend}[/yellow]: {rec}")

    # IP Guard: verifikasi lagi SETELAH semua pencarian selesai — kebocoran
    # baru terlihat saat/ setelah request keluar lewat proxy.
    ok, panic = _verify_ip_guard(
        case_modules.get("ip_guard"), proxy_manager,
        case_modules.get("stats_collector"), phase="post-run",
    )
    if not ok:
        if db:
            db.close()
        if cache:
            cache.close()
        console.print(panic)
        sys.exit(3)

    if db:
        db.close()
    if cache:
        cache.close()


# --------------------------------------------------------------------------- #
# Package manager CLI (atdork install / uninstall / installed / search / ...)
# --------------------------------------------------------------------------- #

PACKAGE_COMMANDS = ("install", "uninstall", "installed", "search", "update", "index")


def _pretty_path(path) -> str:
    """Shorten a path under the user's home directory to ~/..."""
    text = str(path)
    home = os.path.expanduser("~")
    if text.startswith(home):
        return "~" + text[len(home):]
    return text


def _print_ref_error(exc: PackageError) -> None:
    """Print a package error (with suggestions when available)."""
    console.print(f"[red]Error: {exc}[/red]")
    if isinstance(exc, RefError) and exc.suggestions:
        console.print("[yellow]Did you mean:[/yellow]")
        for suggestion in exc.suggestions:
            console.print(f"  [cyan]{suggestion}[/cyan]")


def _pkg_install(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="atdork install",
        description="Install dork packages from the Atdork-DB repository.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-copy even when the installed file is already identical.",
    )
    parser.add_argument(
        "refs", nargs="+", metavar="REF",
        help="@cve/cve_1.txt, c@cve_1.txt, or a folder ref like @cve",
    )
    args_ = parser.parse_args(argv)

    exit_code = 0
    installed_count = existing_count = total_dorks = 0
    for ref in args_.refs:
        try:
            outcomes = install_packages(ref, force=args_.force)
        except PackageError as exc:
            _print_ref_error(exc)
            exit_code = 1
            continue
        for outcome in outcomes:
            if outcome.status == "exists":
                existing_count += 1
                console.print(
                    f"[dim]• {outcome.entry.ref} — already installed "
                    f"({outcome.entry.dork_lines} dorks)[/dim]"
                )
            else:
                installed_count += 1
                total_dorks += outcome.entry.dork_lines
                verb = "updated" if outcome.status == "updated" else "installed"
                console.print(
                    f"[green]✔[/green] {outcome.entry.ref} — {verb} "
                    f"({outcome.entry.dork_lines} dorks)"
                )
    summary_bits = []
    if installed_count:
        summary_bits.append(f"{installed_count} installed")
    if existing_count:
        summary_bits.append(f"{existing_count} already present")
    if summary_bits:
        console.print(
            f"[bold cyan]Done:[/bold cyan] {', '.join(summary_bits)}"
            + (f" — {total_dorks} dorks" if total_dorks else "")
        )
        console.print(f"[dim]Store: {_pretty_path(get_package_store_hint())}[/dim]")
    return exit_code


def get_package_store_hint() -> str:
    from core.package_manager import get_package_dir
    return str(get_package_dir())


def _pkg_uninstall(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="atdork uninstall",
        description="Remove installed packages from the local store.",
    )
    parser.add_argument("refs", nargs="+", metavar="REF", help="Package refs to remove.")
    args_ = parser.parse_args(argv)

    exit_code = 0
    for ref in args_.refs:
        try:
            removed, missing = uninstall_packages(ref)
        except PackageError as exc:
            _print_ref_error(exc)
            exit_code = 1
            continue
        for entry in removed:
            console.print(f"[green]✔[/green] Removed {entry.ref}")
        for entry in missing:
            console.print(f"[dim]• Not installed: {entry.ref}[/dim]")
        if not removed and not missing:  # pragma: no cover - defensive
            exit_code = 1
    return exit_code


def _pkg_installed(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="atdork installed",
        description="List packages installed in the local store.",
    )
    parser.parse_args(argv)

    packages = list_installed()
    if not packages:
        console.print("[yellow]No packages installed yet.[/yellow]")
        console.print(
            "[dim]Try: atdork install c@cve_1.txt — "
            "use 'atdork search <keyword>' to browse the index.[/dim]"
        )
        return 0

    status_label = {
        "ok": "[green]up to date[/green]",
        "modified": "[yellow]modified locally[/yellow]",
        "orphan": "[dim]not in index[/dim]",
    }
    table = Table(
        title=f"Installed packages ({len(packages)})",
        title_style="bold cyan",
        show_lines=False,
    )
    table.add_column("Ref", style="cyan", no_wrap=True)
    table.add_column("Dorks", justify="right", style="green", width=8)
    table.add_column("Size", justify="right", style="yellow", width=10)
    table.add_column("Status")
    for pkg in packages:
        table.add_row(
            f"@{pkg.folder}/{pkg.name}",
            str(pkg.dork_lines),
            _format_size(pkg.size_bytes),
            status_label.get(pkg.status, pkg.status),
        )
    console.print(table)
    console.print(f"[dim]Store: {_pretty_path(get_package_store_hint())}[/dim]")
    return 0


def _pkg_search(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="atdork search",
        description="Search the Atdork-DB package index (Index.idn).",
    )
    parser.add_argument("query", nargs="+", metavar="KEYWORD", help="Keywords to search for.")
    parser.add_argument("--limit", type=int, default=30, help="Maximum rows to display (default 30).")
    args_ = parser.parse_args(argv)

    matches = search_index(" ".join(args_.query))
    if not matches:
        console.print(f"[yellow]No packages match {' '.join(args_.query)!r}.[/yellow]")
        console.print("[dim]Tip: folder names count too — try 'atdork search cve'.[/dim]")
        return 1

    shown = matches[: max(1, args_.limit)]
    table = Table(
        title=f"Matches ({len(matches)})",
        title_style="bold cyan",
        show_lines=False,
    )
    table.add_column("Ref", style="cyan", no_wrap=True)
    table.add_column("Dorks", justify="right", style="green", width=8)
    table.add_column("Size", justify="right", style="yellow", width=10)
    table.add_column("Description")
    for entry in shown:
        table.add_row(
            entry.ref, str(entry.dork_lines),
            _format_size(entry.size_bytes), entry.description,
        )
    console.print(table)
    if len(matches) > len(shown):
        console.print(f"[dim]… {len(matches) - len(shown)} more matches (raise --limit).[/dim]")
    console.print(
        "[dim]Install with: "
        f"atdork install {shown[0].ref}[/dim]"
    )
    return 0


def _pkg_update(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="atdork update",
        description="Pull the latest data from the Atdork-DB repository.",
    )
    parser.parse_args(argv)

    try:
        ok, message = update_repo()
    except PackageError as exc:
        _print_ref_error(exc)
        return 1
    if ok:
        console.print(f"[green]✔ Atdork-DB updated:[/green] {message}")
        try:
            stats = build_pkg_index()
            console.print(
                f"[dim]Index refreshed: {stats['entries']} entries, "
                f"{stats['total_dorks']} dorks.[/dim]"
            )
        except PackageError as exc:
            console.print(f"[yellow]Warning: could not rebuild index: {exc}[/yellow]")
        return 0
    console.print(f"[red]Error: update failed:[/red] {message}")
    return 1


def _pkg_index(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="atdork index",
        description="Show or rebuild the Atdork-DB index (Index.idn).",
    )
    parser.add_argument("--build", action="store_true", help="Rescan @folders and rewrite Index.idn.")
    parser.add_argument("--repo", type=str, help="Atdork-DB path override.")
    args_ = parser.parse_args(argv)

    # Env aktif: index rebuild menulis Index.idn — repo wajib dalam root env.
    if args_.repo:
        try:
            args_.repo = guard_if_env(args_.repo)
        except EnvError as exc:
            console.print(f"[red]Environment error: {exc}[/red]")
            return 1

    if args_.build:
        try:
            stats = build_pkg_index(repo=args_.repo)
        except PackageError as exc:
            _print_ref_error(exc)
            return 1
        console.print(
            f"[green]✔ Index rebuilt:[/green] {stats['entries']} entries in "
            f"{stats['folders']} folders — {stats['total_dorks']} dorks"
        )
        console.print(f"[dim]{_pretty_path(stats['path'])}[/dim]")
        return 0

    try:
        repo = find_db_repo(args_.repo)
        header = read_index_header(args_.repo)
        entries = load_index(repo=args_.repo)
    except PackageError as exc:
        _print_ref_error(exc)
        return 1
    console.print(f"[bold cyan]Index:[/bold cyan] {_pretty_path(repo / 'Index.idn')}")
    console.print(
        f"  entries: {len(entries)}   folders: {len({e.folder for e in entries})}   "
        f"dorks: {sum(e.dork_lines for e in entries)}"
    )
    if header.get("generated"):
        console.print(f"  generated: {header['generated']}")
    console.print("[dim]Rebuild with: atdork index --build[/dim]")
    return 0


def package_cli(argv: List[str]) -> int:
    """Dispatch a package-manager subcommand; returns a process exit code."""
    if not argv or argv[0] not in PACKAGE_COMMANDS:
        console.print(
            "[red]Error: unknown package command.[/red]\n"
            f"[dim]Available: {', '.join(PACKAGE_COMMANDS)}[/dim]"
        )
        return 2

    if argv[0] in ("-h", "--help"):  # pragma: no cover - dispatch filters this
        return 0

    handlers = {
        "install": _pkg_install,
        "uninstall": _pkg_uninstall,
        "installed": _pkg_installed,
        "search": _pkg_search,
        "update": _pkg_update,
        "index": _pkg_index,
    }
    try:
        return handlers[argv[0]](argv[1:])
    except PackageError as exc:
        _print_ref_error(exc)
        return 1
    except KeyboardInterrupt:  # pragma: no cover - interactive
        console.print("\n[yellow]⚠️ Cancelled[/yellow]")
        return 130


# ── Environment (workspace) CLI ────────────────────────────────────────────

def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"  # pragma: no cover


def _cli_passed(argv, *flags) -> bool:
    """Did the user pass one of these flags explicitly on the CLI?"""
    for tok in argv:
        for f in flags:
            if tok == f:
                return True
            if f.startswith("--") and tok.startswith(f + "="):
                return True
            if f == "-o" and tok.startswith("-o") and not tok.startswith("--"):
                return True
    return False


def apply_env_to_args(args, workspace, argv=None) -> None:
    """Redirect every path-ish argument into the environment (strict guard).

    Values coming from the CLI are kept but constrained to the root
    (EnvEscapeError when they resolve outside); values from defaults/config
    are replaced with the env-owned locations.
    """
    argv = list(argv if argv is not None else sys.argv[1:])

    def pick(cli_flags, attr, env_path):
        if _cli_passed(argv, *cli_flags):
            setattr(args, attr, str(workspace.guard_write(getattr(args, attr))))
        else:
            setattr(args, attr, str(env_path))

    pick(("--output-dir",), "output_dir", workspace.results_dir)
    if args.output:
        if _cli_passed(argv, "-o", "--output"):
            args.output = str(workspace.guard_write(args.output))
        else:
            args.output = str(workspace.results_dir / os.path.basename(args.output))
    pick(("--log-file",), "log_file", workspace.log_file)
    pick(("--db-path",), "db_path", workspace.db_path)
    pick(("--cache-db",), "cache_db", workspace.cache_db)
    pick(("--package-dir",), "package_dir", workspace.packages_dir)
    pick(("--db-repo",), "db_repo", workspace.db_repo)

    # Explicit extra write targets — constrain when set.
    if args.database_path:
        args.database_path = str(workspace.guard_write(args.database_path))
    if args.export_db:
        if _cli_passed(argv, "--export-db"):
            args.export_db = str(workspace.guard_write(args.export_db))
        else:
            args.export_db = str(workspace.state_dir / os.path.basename(args.export_db))
    if args.ghdb_file:
        if _cli_passed(argv, "--ghdb-file"):
            args.ghdb_file = str(workspace.guard_write(args.ghdb_file))
        else:
            args.ghdb_file = str(workspace.results_dir / os.path.basename(args.ghdb_file))

    # Extraction destinations are write targets too: without this, the strict
    # write guard could be bypassed via '--extract-database-to /anywhere'.
    if args.database_dork_extract:
        if _cli_passed(argv, "--database-dork-extract"):
            args.database_dork_extract = str(workspace.guard_write(args.database_dork_extract))
        else:
            args.database_dork_extract = str(
                workspace.results_dir / os.path.basename(args.database_dork_extract)
            )
    if args.extract_database_to:
        if _cli_passed(argv, "--extract-database-to"):
            args.extract_database_to = str(workspace.guard_write(args.extract_database_to))
        else:
            args.extract_database_to = str(
                workspace.results_dir / os.path.basename(args.extract_database_to)
            )
    elif args.extract_database:
        # '--extract-database' with the default destination writes './database'
        # relative to CWD; keep it inside the environment instead.
        args.extract_database_to = str(workspace.results_dir / "database")


def env_cli(argv: List[str]) -> int:
    """`atdork env create|init|list|use|which|info|destroy` → exit code."""
    import argparse as _argparse
    from core.env import (
        Env, MARKER_NAME, create_env, destroy_env, list_env_roots,
        read_registry, set_active_env,
    )

    parser = _argparse.ArgumentParser(
        prog="atdork env",
        description="Manage isolated AtDork environments: one root folder that "
                    "holds results, logs, cache, state, config and the "
                    "Atdork-DB checkout.",
    )
    sub = parser.add_subparsers(dest="action")
    p_create = sub.add_parser("create", aliases=["init"],
                              help="Create an environment at <path> (idempotent).")
    p_create.add_argument("path")
    p_create.add_argument("--name", type=str, default=None)
    p_create.add_argument("--force", action="store_true",
                          help="Rewrite the marker file (new name/timestamp).")
    sub.add_parser("list", help="List registered environments.")
    p_use = sub.add_parser("use", help="Set the default active environment.")
    p_use.add_argument("path")
    sub.add_parser("which", help="Show the resolved environment and its paths.")
    sub.add_parser("info", help="Show environment size and status.")
    p_destroy = sub.add_parser("destroy",
                               help="Unregister an environment (keeps files unless --delete).")
    p_destroy.add_argument("path")
    p_destroy.add_argument("--delete", action="store_true",
                           help="Also delete the environment folder (asks for confirmation).")
    args_ = parser.parse_args(argv)

    try:
        if args_.action in ("create", "init"):
            env = create_env(args_.path, name=args_.name, force=args_.force)
            console.print(f"[green]✔ Environment ready:[/green] {env.root}")
            for key, value in env.describe_paths().items():
                console.print(f"  [dim]{key:8}[/dim] {value}")
            console.print(
                f"\n[dim]Use it:[/dim] atdork --env {env.root} -q \"...\"  "
                f"[dim]or set as default:[/dim] atdork env use {env.root}"
            )
            return 0

        if args_.action == "list":
            reg = read_registry()
            roots = list_env_roots()
            if not roots:
                console.print("[dim]No environments registered. "
                              "Create one with: atdork env create <path>[/dim]")
                return 0
            for root in roots:
                tags = ""
                if root == reg.get("active"):
                    tags += " [green](active)[/green]"
                if Env.at(root) is None:
                    tags += " [red](missing)[/red]"
                console.print(f"  {root}{tags}")
            return 0

        if args_.action == "use":
            env = Env.at(args_.path)
            if env is None:
                raise EnvError(
                    f"'{args_.path}' is not an AtDork environment "
                    f"(missing {MARKER_NAME}). Create it first: "
                    f"atdork env create {args_.path}"
                )
            set_active_env(env.root)
            console.print(f"[green]✔ Active environment:[/green] {env.root}")
            return 0

        if args_.action == "which":
            env = resolve_env()
            if env is None:
                console.print("[yellow]No environment active.[/yellow] "
                              "(--env, ATDORK_ENV, or 'atdork env use <path>')")
                return 0
            console.print(f"[green]✔ Environment:[/green] {env.root}"
                          + (f" [dim]({env.name})[/dim]" if env.name else ""))
            for key, value in env.describe_paths().items():
                console.print(f"  [dim]{key:8}[/dim] {value}")
            return 0

        if args_.action == "info":
            env = resolve_env()
            if env is None:
                console.print("[yellow]No environment active.[/yellow] "
                              "(--env, ATDORK_ENV, or 'atdork env use <path>')")
                return 1
            created = env.meta.get("created_at", "?")
            console.print(f"[green]✔ Environment:[/green] {env.root} "
                          f"[dim](name: {env.name or '-'}, created: {created})[/dim]")
            console.print("  [dim]usage by area:[/dim]")
            for rel, total in env.usage_bytes().items():
                console.print(f"    {rel:18} {_fmt_bytes(total)}")
            n_results = sum(len(files) for _r, _d, files in os.walk(env.results_dir))
            console.print(f"  [dim]results files:[/dim] {n_results}")
            console.print(
                f"  [dim]db repo:[/dim] "
                + ("ready" if env.db_repo.is_dir()
                   else "not cloned yet (run: atdork update)")
            )
            return 0

        if args_.action == "destroy":
            if args_.delete:
                from rich.prompt import Confirm
                if not Confirm.ask(
                    f"Delete environment '{args_.path}' and ALL files inside it?"
                ):
                    console.print("[yellow]Cancelled.[/yellow]")
                    return 1
            destroy_env(args_.path, delete_files=args_.delete)
            console.print(
                "[green]✔ Environment removed[/green] "
                + ("(folder deleted)" if args_.delete
                   else "(unregistered; files kept on disk)")
            )
            return 0

        parser.print_help()
        return 2
    except EnvError as exc:
        console.print(f"[red]Environment error: {exc}[/red]")
        return 1


# ── Workflow engine (fase 3) ───────────────────────────────────────────────

def _collect_workflow_definitions(workspace, files=None):
    """Merge workflow definitions from config `workflows:` + files.

    Without explicit files, the root is scanned for workflow.yaml (env root
    first, then the CWD). Returns ({name: (definition, source)}, paths).
    """
    config_workflows = get_setting("workflows")
    paths = list(files) if files else discover_workflow_files(workspace)
    return collect_workflows(
        paths, config_workflows if isinstance(config_workflows, dict) else {}
    ), paths


def _resolve_workflow(name: str, workspace, files=None):
    """Resolve *name* to ``(workflow_name, definition, source)``.

    Accepts a workflow name (config or discovered files), an explicit file
    path (runnable when it holds exactly one workflow), or a directory marker
    such as ``.`` (the single workflow discovered in that root is used).
    """
    if name and os.path.isfile(name):
        workflows = load_workflow_file(name)
        if len(workflows) == 1:
            wname, definition = next(iter(workflows.items()))
            return wname, definition, name
        raise WorkflowError(
            f"{name} contains {len(workflows)} workflows "
            f"({', '.join(sorted(workflows))}); pass the name explicitly"
        )

    if name == "." or (name and os.path.isdir(name)):
        base = Path(name) if name != "." else Path.cwd()
        found = discover_workflow_files(workspace, cwd=base)
        collected = collect_workflows(found)
        if not collected:
            raise WorkflowError(
                f"No workflow file found in '{base}' "
                f"(expected one of: {', '.join(WORKFLOW_FILENAMES)})"
            )
        if len(collected) > 1:
            raise WorkflowError(
                f"'{base}' holds {len(collected)} workflows "
                f"({', '.join(sorted(collected))}); pick one by name"
            )
        wname, (definition, source) = next(iter(collected.items()))
        return wname, definition, source

    collected, paths = _collect_workflow_definitions(workspace, files)
    if name in collected:
        definition, source = collected[name]
        return name, definition, source
    available = ", ".join(sorted(collected)) or "(none)"
    sources = ", ".join(str(p) for p in paths) or "no files"
    raise WorkflowError(
        f"Workflow '{name}' not found. Available: {available} "
        f"[dim](sources: config workflows:, {sources})[/dim]"
    )


def _print_workflow_summary(summary: Dict[str, Any], source: str) -> None:
    """Compact per-step result table after a run."""
    marks = {
        "done": ("✓", "green"), "below_threshold": ("△", "yellow"),
        "failed": ("✗", "red"), "planned": ("•", "cyan"),
    }
    for step in summary.get("steps", []):
        mark, color = marks.get(step.get("status", ""), ("•", "dim"))
        status_text = str(step.get("status", ""))
        if "results" in step:
            status_text += f", {step.get('results', 0)} results"
        if step.get("skipped"):
            status_text += ", skipped"
        line = f"  [{color}]{mark}[/{color}] {escape(str(step.get('name')))} [dim]({status_text})[/dim]"
        if step.get("error"):
            line += f" [red]{escape(str(step['error']))}[/red]"
        console.print(line)
    status = summary.get("status", "completed")
    color = "green" if status == "completed" else "red"
    console.print(
        f"[{color}]Workflow {status}[/{color}] — "
        f"{summary.get('total_results', 0)} total unique results "
        f"[dim](source: {escape(str(source))}, run {summary.get('run_id')}, "
        f"state: {escape(str(summary.get('state_file')))})[/dim]"
    )


def _run_workflow_by_name(name: str, workspace, *, files=None, target=None,
                          workers=None, step=None, resume=False,
                          dry_run=False) -> int:
    """Shared execution path for `atdork workflow run` and --run-workflow."""
    wname, definition, source = _resolve_workflow(name, workspace, files)
    engine = WorkflowEngine(
        wname, definition, target=target, workers=workers,
        workspace=workspace, console=console,
    )
    try:
        summary = engine.run(resume=resume, only_step=step, dry_run=dry_run)
    except WorkflowError as exc:
        console.print(f"[red]Workflow error: {exc}[/red]")
        return 1
    _print_workflow_summary(summary, source)
    return 0 if summary.get("status") == "completed" else 1


def workflow_cli(argv: List[str], workspace=None) -> int:
    """`atdork workflow list|validate|run` — sequential dork campaigns."""
    parser = argparse.ArgumentParser(
        prog="atdork workflow",
        description="Run sequential multi-step dork campaigns from YAML "
                    "definitions (config 'workflows:' section or workflow.yaml "
                    "in the root).",
    )
    sub = parser.add_subparsers(dest="command")

    p_list = sub.add_parser("list", help="List available workflows.")
    p_list.add_argument("--file", action="append", dest="files", metavar="FILE",
                        help="Workflow YAML file (repeatable).")

    p_validate = sub.add_parser("validate", help="Validate workflow definitions.")
    p_validate.add_argument("name", nargs="?", default=None,
                            help="Workflow name (default: all).")
    p_validate.add_argument("--file", action="append", dest="files", metavar="FILE",
                            help="Workflow YAML file (repeatable).")

    p_run = sub.add_parser("run", help="Run a workflow.")
    p_run.add_argument("name",
                       help="Workflow name, a file path, or '.' for the single "
                            "workflow discovered in the current root.")
    p_run.add_argument("--file", action="append", dest="files", metavar="FILE",
                       help="Workflow YAML file (repeatable).")
    p_run.add_argument("--target", help="Override the workflow target ({target}).")
    p_run.add_argument("--workers", type=int, help="Override worker (thread) count.")
    p_run.add_argument("--step", help="Run only this step (by name).")
    p_run.add_argument("--resume", action="store_true",
                       help="Skip steps already completed in the saved state.")
    p_run.add_argument("--dry-run", action="store_true",
                       help="Print resolved queries without searching.")

    if not argv:
        parser.print_help()
        return 1
    args = parser.parse_args(argv)

    try:
        if args.command == "list":
            collected, paths = _collect_workflow_definitions(workspace, args.files)
            if not collected:
                console.print("[yellow]No workflows found.[/yellow] "
                              "Add a 'workflows:' section to your config or a "
                              "workflow.yaml file in the root.")
                return 0
            for wname in sorted(collected):
                definition, source = collected[wname]
                steps = len(definition.get("steps") or []) \
                    if isinstance(definition, dict) else 0
                desc = definition.get("description", "") \
                    if isinstance(definition, dict) else ""
                console.print(f"  [cyan]{wname}[/cyan] — {steps} step(s) "
                              f"[dim]({escape(str(source))})[/dim]"
                              + (f" {desc}" if desc else ""))
            return 0

        if args.command == "validate":
            collected, _ = _collect_workflow_definitions(workspace, args.files)
            if args.name:
                if args.name not in collected:
                    raise WorkflowError(
                        f"Workflow '{args.name}' not found. Available: "
                        f"{', '.join(sorted(collected)) or '(none)'}"
                    )
                collected = {args.name: collected[args.name]}
            if not collected:
                raise WorkflowError("No workflows to validate (none configured "
                                    "and none discovered).")
            invalid = False
            for wname, (definition, _source) in sorted(collected.items()):
                errors = validate_workflow(wname, definition)
                if errors:
                    invalid = True
                    console.print(f"[red]✗ {wname}[/red]:")
                    for error in errors:
                        console.print(f"    [red]- {error}[/red]")
                else:
                    steps = len((definition or {}).get("steps") or [])
                    console.print(f"[green]✓ {wname}[/green] — valid "
                                  f"({steps} steps)")
            return 1 if invalid else 0

        if args.command == "run":
            return _run_workflow_by_name(
                args.name, workspace, files=args.files, target=args.target,
                workers=args.workers, step=args.step, resume=args.resume,
                dry_run=args.dry_run,
            )
    except WorkflowError as exc:
        console.print(f"[red]Workflow error: {exc}[/red]")
        return 1

    parser.print_help()
    return 2


# ── Plugin system ──────────────────────────────────────────────────────────

def _coerce_plugin_option(definition: PluginDef, opt_name: str, raw: str) -> Any:
    """Convert an ``--opt key=value`` string using the option's contract."""
    match = next((o for o in definition.options
                  if o["name"] == opt_name
                  or o["name"].replace("-", "_") == opt_name), None)
    if match is None:
        raise PluginError(
            f"plugin '{definition.name}' has no option '{opt_name}'. "
            f"Known: {', '.join(o['name'] for o in definition.options) or '(none)'}"
        )
    if match.get("action") == "store_true":
        value = raw.strip().lower()
        if value in ("1", "true", "yes", "on"):
            return True
        if value in ("0", "false", "no", "off"):
            return False
        raise PluginError(f"'{opt_name}' is a switch — use "
                          f"{definition.flag_for(match['name'])} or key=true/false")
    if match.get("type") == "int":
        try:
            return int(raw)
        except ValueError as e:
            raise PluginError(f"'{opt_name}' expects an integer, got {raw!r}") from e
    if match.get("type") == "float":
        try:
            return float(raw)
        except ValueError as e:
            raise PluginError(f"'{opt_name}' expects a number, got {raw!r}") from e
    choices = match.get("choices")
    if isinstance(choices, list) and raw not in choices:
        raise PluginError(f"'{opt_name}' must be one of: {', '.join(choices)}")
    return raw


def plugins_cli(argv: List[str], workspace=None) -> int:
    """`atdork plugins list|info|run` — inspect and launch installed plugins."""
    parser = argparse.ArgumentParser(
        prog="atdork plugins",
        description="Plugin tools installed via the package manager. Run them "
                    "with the flag syntax 'atdork --<plugin> "
                    "--<plugin>-<option> ...' or via 'plugins run'.",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List discovered plugins.")
    p_info = sub.add_parser("info", help="Show a plugin's contract and flags.")
    p_info.add_argument("name")
    p_run = sub.add_parser("run", help="Run a plugin (alternative to flag syntax).")
    p_run.add_argument("name")
    p_run.add_argument("--opt", action="append", default=[], metavar="KEY=VALUE",
                       help="Plugin option override (repeatable).")

    if not argv:
        parser.print_help()
        return 1
    args_ = parser.parse_args(argv)

    try:
        if args_.command == "list":
            definitions = discover_plugins()
            if not definitions:
                console.print("[yellow]No plugins found.[/yellow] Install one: "
                              "atdork install @plugins/<tool> — or add folders "
                              "via plugins.paths in your config.")
                return 0
            for definition in sorted(definitions, key=lambda d: d.name):
                if definition.error:
                    status = f"[red]invalid[/red]: {definition.error}"
                elif not definition.enabled:
                    status = "[dim]disabled (plugins.enabled/disabled)[/dim]"
                else:
                    status = "[green]ready[/green]"
                console.print(f"  [cyan]{definition.name}[/cyan] "
                              f"v{definition.version or '?'} — "
                              f"{definition.description or '(no description)'}")
                console.print(
                    f"      {status} [dim]| trigger --{definition.name} | "
                    f"{len(definition.options)} option(s) | {definition.path}[/dim]"
                )
            return 0

        if args_.command == "info":
            definitions = {d.name: d for d in discover_plugins()}
            definition = definitions.get(args_.name)
            if definition is None:
                raise PluginError(
                    f"Plugin '{args_.name}' not found. Installed: "
                    f"{', '.join(sorted(definitions)) or '(none)'}"
                )
            console.print(f"[bold cyan]{definition.name}[/bold cyan] "
                          f"v{definition.version or '?'} — {definition.description}")
            console.print(f"  [dim]source:[/dim] {definition.source}")
            console.print(f"  [dim]path:  [/dim] {definition.path}")
            console.print(f"  [dim]ref:   [/dim] {definition.ref}")
            console.print(f"  [dim]status:[/dim] "
                          + ("INVALID: " + definition.error if definition.error
                             else ("enabled" if definition.enabled else "disabled")))
            console.print(f"  [dim]run:   [/dim] atdork --{definition.name} "
                          f"[--{definition.name}-<option> ...]")
            if definition.options:
                table = Table(show_header=True, header_style="bold")
                table.add_column("Flag")
                table.add_column("Dest")
                table.add_column("Type")
                table.add_column("Default")
                table.add_column("Choices")
                table.add_column("Help")
                for opt in definition.options:
                    flag = definition.flag_for(opt["name"])
                    table.add_row(
                        flag, flag[2:].replace("-", "_"),
                        str(opt.get("type", "store_true" if opt.get("action") == "store_true" else "str")),
                        repr(opt.get("default")),
                        ", ".join(opt["choices"]) if isinstance(opt.get("choices"), list) else "",
                        str(opt.get("help", "")),
                    )
                console.print(table)
            return 0

        if args_.command == "run":
            definitions = {d.name: d for d in discover_plugins()}
            definition = definitions.get(args_.name)
            if definition is None:
                raise PluginError(
                    f"Plugin '{args_.name}' not found. Installed: "
                    f"{', '.join(sorted(definitions)) or '(none)'}"
                )
            if definition.error:
                raise PluginError(f"Plugin '{definition.name}' is invalid: "
                                  f"{definition.error}")
            namespace = vars(build_parser().parse_args([]))
            namespace[definition.name] = True
            for assignment in args_.opt or []:
                key, sep, value = assignment.partition("=")
                if not sep:
                    raise PluginError(
                        f"--opt expects KEY=VALUE, got {assignment!r}"
                    )
                key = key.strip().lstrip("-")
                namespace[f"{definition.name}_{key}".replace("-", "_")] = \
                    _coerce_plugin_option(definition, key, value.strip())
            ctx = make_context(workspace=workspace, console=console)
            console.print(f"[magenta]▶ plugin[/magenta] {definition.name} "
                          f"[dim]({definition.path})[/dim]")
            return run_plugin(definition, argparse.Namespace(**namespace), ctx)
    except PluginError as exc:
        console.print(f"[red]Plugin error:[/red] {exc}")
        return 1

    parser.print_help()
    return 2


def main():
    # 1. Parser minimal khusus untuk --config
    config_parser = argparse.ArgumentParser(add_help=False)
    config_parser.add_argument("--config", type=str, default=None)
    config_parser.add_argument("--env", type=str, default=None)
    config_args, remaining = config_parser.parse_known_args()

    # 1b. Resolve AtDork environment (workspace) — before config load, so the
    #     env layer joins config discovery and `atdork env ...` works even
    #     with a broken config file.
    if remaining and remaining[0] == "env":
        sys.exit(env_cli(remaining[1:]))
    try:
        workspace = resolve_env(config_args.env)
    except EnvError as e:
        console.print(f"[red]Environment error: {e}[/red]")
        sys.exit(1)

    # 2. Muat konfigurasi SELALU (auto-discover atdork.yaml/AtDork.yaml di CWD
    #    + env ATDORK_*), bukan hanya saat --config diberikan (bug lama:
    #    tanpa --config, file config & env var diabaikan total).
    raw_config = {}
    if config_args.config and not os.path.isfile(config_args.config):
        console.print(f"[red]Error: Config file not found: {config_args.config}[/red]")
        sys.exit(1)

    try:
        loaded = load_config(
            config_args.config,
            env_config_path=str(workspace.config_file) if workspace else None,
        )
        if isinstance(loaded, dict):
            raw_config = loaded
        elif loaded is not None:
            console.print("[yellow]Warning: Config file did not yield a dictionary, using defaults.[/yellow]")
    except ConfigError as e:
        # Invalid schema / missing ${ENV} for a configured engine → fail fast
        # with a clear, actionable message instead of silently misbehaving.
        console.print(f"[red]Config error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error loading config file: {e}[/red]")
        console.print("[yellow]Continuing with default values...[/yellow]")

    # Normalisasi kunci: ganti tanda '-' menjadi '_' agar cocok dengan argparse dest
    config = {k.replace('-', '_'): v for k, v in raw_config.items()}

    # --- Environment (workspace): lokasi store DB & package dimiliki env ---
    # Package manager membaca kunci ini lewat config (get_setting), bukan args,
    # jadi di-inject ke dua tempat: raw_config (→ argparse defaults) dan
    # _CURRENT (→ get_setting).
    if workspace:
        for key, value in (("package_dir", str(workspace.packages_dir)),
                           ("db_repo", str(workspace.db_repo))):
            raw_config[key] = value
            override_setting(key, value)

    # --- Package manager subcommands (atdork install / search / ...) ---
    # Dispatched before the full parser so they don't clash with search flags.
    if remaining and remaining[0] in PACKAGE_COMMANDS:
        sys.exit(package_cli(remaining))

    # --- Workflow engine subcommands (atdork workflow list/validate/run) ---
    # Needs the loaded config (`workflows:` layers) and the env workspace
    # (state + guarded outputs), so it dispatches after both are resolved.
    if remaining and remaining[0] == "workflow":
        sys.exit(workflow_cli(remaining[1:], workspace))

    # --- Plugin management (atdork plugins list|info|run) ---
    if remaining and remaining[0] == "plugins":
        sys.exit(plugins_cli(remaining[1:], workspace))

    # 3. Bangun parser penuh
    parser = build_parser()

    # 4. Hanya terapkan kunci yang valid (dikenali oleh parser).
    #    Kunci berupa section v2 (search/engines/profiles/...) sengaja tidak
    #    diterapkan ke parser — mereka dibaca modul via get_setting().
    v2_section_keys = {"search", "engines", "profiles", "resilience",
                       "output", "workflows", "version", "plugins"}
    valid_dests = {action.dest for action in parser._actions if action.dest != 'help'}
    filtered_config = {k: v for k, v in config.items() if k in valid_dests}
    ignored = set(config.keys()) - set(filtered_config.keys()) - v2_section_keys
    if ignored:
        console.print(f"[dim]Unknown config keys ignored: {', '.join(sorted(ignored))}[/dim]")

    parser.set_defaults(**filtered_config)

    # 5. Parse seluruh command line
    args = parser.parse_args(remaining)

    # 5b. Environment aktif → semua tulisan dipaksa ke dalam root env
    #     (strict path guard: nilai dari CLI yang keluar root = error).
    if workspace:
        try:
            apply_env_to_args(args, workspace)
        except EnvError as e:
            console.print(f"[red]Environment error: {e}[/red]")
            sys.exit(1)

    setup_logging(debug=args.debug, log_file=args.log_file)

    # --- Workflow engine (--run-workflow NAME) ---
    # Runs a sequential multi-step campaign; definitions come from the config
    # `workflows:` section, a workflow.yaml auto-discovered in the root, or
    # an explicit --workflow-file. Dispatched before the interactive check.
    if args.run_workflow:
        sys.exit(_run_workflow_by_name(
            args.run_workflow, workspace,
            files=[args.workflow_file] if args.workflow_file else None,
            target=args.workflow_target, workers=args.workflow_workers,
            resume=args.workflow_resume, dry_run=args.workflow_dry_run,
        ))

    # --- Plugin flags (--<plugin> / --<plugin>-<option>) ---
    # The trigger is the bare --<plugin> flag or ANY --<plugin>-* argument on
    # the command line (config defaults alone never launch a plugin).
    plugin_exit = dispatch_plugin(args, remaining, workspace=workspace,
                                  console=console)
    if plugin_exit is not None:
        sys.exit(plugin_exit)

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

    # Check if interactive mode or no action parameters provided
    has_action = (
        args.query or
        args.batch_file or
        args.resume or
        args.history or
        args.export_db or
        args.template or
        args.list_templates or
        args.preview or
        # NEW (v1.3.9.5) — extraction triggers
        args.extract_database or
        args.database_dork_extract or
        args.extract_database_to or
        args.list_database_dork or
        args.database_dork
    )
    should_interactive = args.interactive or (not has_action)

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
        console.print("\n[yellow]⚠️ Cancelled[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        sys.exit(1)
