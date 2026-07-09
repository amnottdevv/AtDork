# AtDork – Professional OSINT Dorking Tool

![Version](https://img.shields.io/badge/version-1.3.9.6-blue.svg)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-linux%20%7C%20macos%20%7C%20windows-lightgrey)
![Tests](https://img.shields.io/badge/tests-114%20passed-brightgreen)
![Lines](https://img.shields.io/badge/total%20lines-11%2C000%2B-orange)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/atdork?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=pypi+downloads)](https://pepy.tech/projects/atdork)
[![Welcome New Contributor](https://github.com/amnottdevv/AtDork/actions/workflows/welcome_new_contributor.yml/badge.svg)](https://github.com/amnottdevv/AtDork/actions/workflows/welcome_new_contributor.yml)

**AtDork** is a powerful, ethical OSINT tool that performs advanced search queries (Google Dorks) across multiple search engines simultaneously. Designed for security researchers, penetration testers, and bug bounty hunters.

---

## Why AtDork?

- 🚀 **Blazing fast** – Multi‑threaded batch processing with configurable concurrency.
- 🔍 **Multi‑engine** – Queries DuckDuckGo, Google, Bing, Startpage, Yandex, Yahoo, and more.
- 🛡️ **Anonymous** – Built‑in proxy rotation, Tor integration, strict mode to prevent IP leaks. IP leak detection (`--ip-guard`) stops the scan immediately if your real IP is exposed.
- 🧹 **Clean results** – Automatic spam filtering, URL validation, and deduplication.
- 📊 **Professional output** – Export to JSON, CSV, TXT; SQLite database for history and resume. CSV exports are protected against formula injection.
- 🎯 **Smart filtering** – Vulnerability signature detection for WordPress, Joomla, SQLi, and more.
- 📝 **Template system** – Curated YAML‑based dork collections for instant productivity.
- 🗂️ **Local dork database** – Load pre-built, categorized dork collections straight from disk (see [Database Dorks](#database-dorks) below).
- 🌐 **GHDB scraper** – Pull fresh dorks directly from the public Exploit-DB Google Hacking Database, filterable by category and year.
- ⚙️ **Highly configurable** – 60+ CLI flags to control every aspect of your search.
- 🔧 **Post‑processing** – Execute external commands on discovered URLs (`--exec`).
- 💾 **Caching** – Cache search results locally to avoid redundant requests and enable offline access.
- 🔒 **Safe logging** – Proxy credentials are automatically redacted from log files to prevent accidental leaks.
- 🔔 **Notifications** – Send batch summaries to Discord, Slack, or Telegram webhooks.

---

## Installation

### From PyPI (Recommended)
```bash
pip install atdork
```

### From Source
```bash
git clone https://github.com/amnottdevv/atdork.git
cd atdork
pip install .
```

### Verify Installation
```bash
atdork --version
# Output: atdork 1.3.9.6
```

---

## Quick Start

### 1. Your First Search
```bash
atdork -q "site:gov filetype:pdf" -r 10
```
This finds PDF files on government websites and displays the top 10 results.

### 2. Save Results to a File
```bash
atdork -q "intitle:index.of mp3" -r 20 --format json -o music.json
```

### 3. Batch Processing
Create a file `dorks.txt`:
```text
site:edu filetype:xls
inurl:admin login
intitle:"index of" "backup"
```

Run them all at once:
```bash
atdork --batch-file dorks.txt -r 30 --format csv -o results.csv
```

### 4. Search with Proxy (Anonymous)
```bash
atdork -q "confidential filetype:docx" --proxy "http://user:pass@proxy:8080" --strict
```

---

## Detailed Usage

### Single Query
```bash
atdork -q "inurl:product.php?id=" -r 50 --backend google --region uk-en --safesearch off
```

| Flag | Purpose |
|------|---------|
| `-q` | Your dork query |
| `-r` | Number of results (max 100) |
| `--backend` | Search engine: `google`, `bing`, `duckduckgo`, `startpage`, `yandex`, `auto` |
| `--region` | Region code: `us-en`, `uk-en`, `de-de`, `ru-ru`, etc. |
| `--safesearch` | `on`, `moderate`, `off` |

### Batch Processing with Multi‑Threading
```bash
atdork --batch-file dorks.txt -r 40 --concurrency 5 --delay 2 --format json -o batch_results.json
```

| Flag | Purpose |
|------|---------|
| `--batch-file` | Text file with one dork per line |
| `--concurrency` | Number of parallel threads (1‑10) |
| `--delay` | Seconds between requests (avoid rate limits) |
| `-o` | Save all results to a single file |
| `--output-dir` | Save each query result as a separate file |

### Template Dorks (Pre‑Built)
List available templates:
```bash
atdork --list-templates
```

Use a template:
```bash
atdork --template sqli --target example.com -r 30
```

Combine multiple templates with custom queries:
```bash
atdork --template sqli,wordpress,exposed_config -q "site:gov filetype:pdf" -r 25
```

Preview what a template will do:
```bash
atdork --template login_panels --preview
```

Run only specific dorks from a template:
```bash
atdork --template sqli --select 1,3,5 -r 20
```

| Flag | Purpose |
|------|---------|
| `--template` | Template name(s), comma‑separated |
| `--target` | Domain to substitute `{target}` in template dorks |
| `--select` | Run specific dork numbers from template |
| `--list-templates` | Show all available templates |
| `--preview` | Show dorks without executing |
| `--template-path` | Custom template folder |

### Database Dorks

AtDork ships with a local, categorized collection of dork files that you can load directly without hitting the network. This is useful for offline prep, reproducible test runs, or building your own batch lists from a known-good set.

```bash
# Extract the bundled dork collection into ./database
atdork --extract-database

# Extract to a custom location, overwriting if it already exists
atdork --extract-database-to mydorks/ --force

# List the available files and how many dorks each contains
atdork --list-database-dork

# Load dorks from one file and run them
atdork --database-dork 01_footholds -r 20

# Combine multiple files
atdork --database-dork 01_footholds,03_sensitive_directories -r 20

# Randomly sample N dorks from the combined set (reproducible with a seed)
atdork --database-dork 01_footholds --database-r 10 --database-seed 42

# Preview what would be loaded without running anything
atdork --database-dork 01_footholds --database-preview

# Point at a custom database root instead of auto-discovery
atdork --database-dork subdir/file --database-path /path/to/custom/db
```

| Flag | Purpose |
|------|---------|
| `--extract-database` | Extract the bundled dork collection to `./database` |
| `--extract-database-to PATH` | Extract to a custom destination |
| `--database-dork-extract PATH` | Shortcut for the two flags above |
| `--force` | Overwrite an existing extraction destination |
| `--list-database-dork` | List available dork files with counts |
| `--database-dork SPEC` | Load dorks from file(s); comma-separated, subdirectories supported |
| `--database-r N` | Randomly select N dorks from the combined set |
| `--database-seed N` | Seed for reproducible `--database-r` selection |
| `--database-path PATH` | Custom database root directory |
| `--database-preview` | Preview loaded dorks without executing them |

> The files are organized by topic (web misconfigurations, exposed directories/files, exposed panels, and similar categories relevant to authorized security testing). Run `atdork --list-database-dork` to see exactly what's available in your build.

### GHDB Scraper

Pull dorks live from the public Exploit-DB Google Hacking Database, with optional category/year filters.

```bash
# Show available GHDB categories and how many dorks each has
atdork --ghdb-scraper --ghdb-list-categories

# Scrape and save dorks about exposed passwords from 2022-2024
atdork --ghdb-scraper --ghdb-categories password --ghdb-years 2022-2024 --ghdb-file dorks.txt

# Limit total results, save as JSON (includes metadata)
atdork --ghdb-scraper --ghdb-categories 9,12 --ghdb-r 50 --ghdb-file dorks.json
```

| Flag | Purpose |
|------|---------|
| `--ghdb-scraper` | Run the GHDB scraper mode |
| `--ghdb-file` | Save results to file (`.json` or `.txt`, auto-detected) |
| `--ghdb-categories` | Filter by category name (partial match) or numeric ID, comma-separated |
| `--ghdb-years` | Filter by year(s), e.g. `2024` or `2020-2023,2024` |
| `--ghdb-r` | Limit total number of dorks returned after filtering |
| `--ghdb-list-categories` | List GHDB categories with dork counts, then exit |

### Proxy & Anonymity
```bash
# Single proxy
atdork -q "target" --proxy "http://user:pass@host:8080"

# Multiple proxies (comma‑separated)
atdork -q "target" --proxy "http://p1:8080,socks5://p2:1080"

# From file
atdork -q "target" --proxy-file proxies.txt

# Tor integration
atdork -q "target" --tor --strict

# Strict mode (fail if all proxies down)
atdork -q "target" --proxy-file proxies.txt --strict

# Proxy management
atdork -q "target" --proxy-file proxies.txt --proxy-cooldown 120 --max-failures 3
```

**Proxy file format (`proxies.txt`):**
```text
# HTTP proxies
http://user:pass@dc1.provider.com:3128
http://user:pass@dc2.provider.com:3128

# SOCKS proxies
socks5://res1.provider.com:1080
socks5h://res2.provider.com:1080

# Comments with # are ignored
```

### Vulnerability Filtering
```bash
# Basic WordPress detection
atdork -q "inurl:wp-content" -r 30 --filter-vuln wordpress

# Link‑only filter (only matches URLs)
atdork -q "site:example.com" --filter-vuln wordpress-link
```

Create your own wordlist files in `wordlists/` folder:
```text
# wordlists/myplatform.txt
wp-content
wp-admin
wp-includes
```

### Resilience & Rate Limiting
```bash
# Enable circuit breaker & backend fallback
atdork --batch-file dorks.txt --resilient

# Adaptive delay based on backend response
atdork --batch-file dorks.txt --adaptive-delay

# Combined
atdork --batch-file dorks.txt --resilient --adaptive-delay --concurrency 5 --delay 2
```

### Output Validation
```bash
# Disable all filtering (keep raw results)
atdork -q "test" --no-validate

# Strict filtering (require non‑empty snippet)
atdork -q "test" --strict-filter

# Granular control
atdork -q "test" --validate-url only --validate-title 10 --validate-desc 50 --validate-spam true
```

### Database & History (SQLite)
```bash
# Resume interrupted batch
atdork --resume

# View search history
atdork --history

# Export database to JSON/CSV
atdork --export-db all_results.json

# Disable duplicate URL detection
atdork -q "test" --no-dedup
```

### IP Leak Detection
```bash
# Halt immediately if your real IP is exposed while using proxies
atdork --batch-file dorks.txt --proxy-file proxies.txt --strict --ip-guard
```

### Post‑Processing
```bash
# Run a command for every discovered URL
atdork -q "inurl:admin" -r 10 --exec "curl -I {} | grep Server"

# Run a command only on URLs flagged as vulnerable
atdork -q "inurl:wp-content" -r 30 --filter-vuln wordpress --exec-on-vuln "wpscan --url {}"
```

### Cache Results
```bash
# Cache search results for 24 hours (default)
atdork -q "site:gov filetype:pdf" -r 20 --cache

# Use cached results only (offline mode)
atdork -q "site:gov filetype:pdf" -r 20 --cache-only

# Clear all cached data
atdork --clear-cache
```

### Notifications

Send batch summaries to Discord, Slack, or Telegram after searches complete.

#### Discord Webhook
```bash
atdork --batch-file dorks.txt -r 20 \
  --notify "discord:https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN"
```

#### Slack Webhook
```bash
atdork --batch-file dorks.txt -r 20 \
  --notify "slack:https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
```

#### Telegram Bot
```bash
# Format: telegram:<bot_token>/<chat_id>
atdork --batch-file dorks.txt -r 20 \
  --notify "telegram:123456789:ABCDefGHIjklmnoPQRstUVwxyz/987654321"
```

#### Notification Options
```bash
# Send notification only if vulnerable results were found
atdork --batch-file dorks.txt --notify "discord:..." --notify-if-vuln
```

**Setup Instructions:**

1. **Discord**: Create a webhook in your server's channel settings > Integrations > Webhooks
2. **Slack**: Create an incoming webhook at api.slack.com/apps > Create New App > Incoming Webhooks
3. **Telegram**: Get your bot token from @BotFather and chat ID by messaging your bot and visiting `https://api.telegram.org/bot<TOKEN>/getUpdates`

---

## Complete Flag Reference

| Flag | Description | Default |
|------|-------------|---------|
| `-q`, `--query` | Search dork query | |
| `-r`, `--max-results` | Maximum results (1‑100) | 20 |
| `--batch-file` | File with one query per line | |
| `--batch-separator` | Separator for inline queries | `;` |
| `-o`, `--output` | Save results to file | |
| `--output-dir` | Save each query to separate file | |
| `--format` | Output format: `txt`, `json`, `csv` | `txt` |
| `-v`, `--verbose` | Show results in batch mode | |
| `--no-snippet` | Hide snippets in terminal | |
| `--template` | Load dork template(s) | |
| `--target` | Domain for template substitution | |
| `--select` | Select specific dorks from template | |
| `--list-templates` | List available templates | |
| `--template-path` | Custom template directory | |
| `--preview` | Preview template dorks | |
| `--extract-database` | Extract bundled dork collection to `./database` | |
| `--extract-database-to` | Custom extraction destination | |
| `--database-dork-extract` | Shortcut: extract to given path | |
| `--force` | Overwrite existing extraction destination | |
| `--list-database-dork` | List available database dork files | |
| `--database-dork` | Load dorks from database file(s) | |
| `--database-r` | Randomly select N dorks from database | |
| `--database-seed` | Seed for reproducible `--database-r` | |
| `--database-path` | Custom database root directory | |
| `--database-preview` | Preview database dorks without running | |
| `--ghdb-scraper` | Run GHDB scraper mode | |
| `--ghdb-file` | Save GHDB results to file | |
| `--ghdb-categories` | Filter GHDB by category name/ID | |
| `--ghdb-years` | Filter GHDB by year(s)/range | |
| `--ghdb-r` | Limit total GHDB results | |
| `--ghdb-list-categories` | List GHDB categories, then exit | |
| `--region` | Search region | `us-en` |
| `--safesearch` | `on`, `moderate`, `off` | `moderate` |
| `--timelimit` | `d`, `w`, `m`, `y` | |
| `--backend` | Search engine(s) | `auto` |
| `--user-agent` | Custom User‑Agent | auto‑rotate |
| `--timeout` | Request timeout (seconds) | 10 |
| `--retries` | Retry attempts on failure | 2 |
| `--delay` | Delay between requests (seconds) | 0 |
| `--proxy` | Comma‑separated proxy URLs | |
| `--proxy-file` | File with proxy URLs | |
| `--tor` | Use Tor SOCKS5 proxy | |
| `--strict` | Fail if all proxies down | |
| `--proxy-cooldown` | Cooldown after proxy failure (seconds) | 60 |
| `--max-failures` | Remove proxy after N failures | 3 |
| `--concurrency` | Parallel threads for batch | 1 |
| `--resilient` | Enable circuit breaker & fallback | |
| `--adaptive-delay` | Enable adaptive rate limiting | |
| `--ip-guard` | Enable IP leak detection | |
| `--exec` | Execute command on each result URL | |
| `--exec-on-vuln` | Execute command on vulnerable results | |
| `--exec-parallel` | Parallel `--exec` processes | 1 |
| `--exec-timeout` | Timeout per `--exec` command (seconds) | 30 |
| `--cache` | Enable result caching | |
| `--cache-db` | Cache database path | `atdork_cache.db` |
| `--cache-ttl` | Cache TTL in hours | 24 |
| `--cache-only` | Use cache only, no network requests | |
| `--clear-cache` | Delete all cache before starting | |
| `--notify` | Send notification to webhook (`<platform>:<url>`) | |
| `--notify-if-vuln` | Only notify if vulnerable results found | |
| `--no-validate` | Disable spam filtering | |
| `--strict-filter` | Strict validation | |
| `--validate-url` | URL validation mode | `all` |
| `--validate-title` | Minimum title length | 5 |
| `--validate-desc` | Minimum description length | 10 |
| `--validate-spam` | Enable spam detection | `true` |
| `--filter-vuln` | Vulnerability platform filter | |
| `--no-fallback-backends` | Disable backend fallback | |
| `--no-verify` | Disable SSL verification | |
| `--log-file` | Log file path | `atdork.log` |
| `--db-path` | SQLite history/dedup database path | `atdork.db` |
| `--resume` | Resume pending queries | |
| `--history` | Show search history | |
| `--no-dedup` | Disable URL deduplication | |
| `--export-db` | Export history database to file | |
| `--config` | YAML config file path | |
| `--interactive` | Interactive mode | |
| `--debug` | Enable debug logging | |
| `--version` | Show version and exit | |

---

## Real‑World Use Cases

### Bug Bounty Reconnaissance with Full Protection
```bash
atdork --template sqli,xss,lfi --target target.com \
  --proxy-file proxies.txt --strict --resilient --ip-guard \
  --format json -o recon.json
```

### Reproducible Recon Runs from the Local Database
```bash
atdork --database-dork 01_footholds,03_sensitive_directories \
  --database-r 25 --database-seed 7 \
  --proxy-file proxies.txt --format json -o recon_batch.json
```

### Finding Admin Panels
```bash
atdork -q 'intitle:"admin panel" inurl:login' -r 30 --backend google --region uk-en
```

### WordPress Vulnerability Scanning with Post‑Processing
```bash
atdork -q "inurl:wp-content site:example.com" -r 40 \
  --filter-vuln wordpress \
  --exec-on-vuln "wpscan --url {} --enumerate p" \
  --exec-parallel 2 --exec-timeout 60
```

### Automated Weekly Monitoring with Notifications
```bash
# Add to crontab (Linux/macOS)
0 6 * * 1 cd /path/to/atdork && atdork --batch-file weekly_dorks.txt --format csv --output-dir /reports/$(date +\%Y-\%W)/ --notify "slack:https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
```

---

## Configuration File

Create `atdork.yaml` for persistent settings:
```yaml
max_results: 30
region: "uk-en"
safesearch: "off"
delay: 1.0
format: "json"
output_dir: "./results"
proxy_file: "proxies.txt"
notify: "discord:https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN"
```

AtDork automatically loads this file from the current directory. CLI flags override YAML values.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **Rate limited (429)** | Add `--delay 3`, use `--proxy-file`, or enable `--adaptive-delay` |
| **No results** | Try different `--backend` (e.g., `startpage`, `yandex`) or `--region` |
| **Proxy fails** | Check format: `scheme://user:pass@host:port` |
| **Batch stuck** | Reduce `--concurrency`, add `--timeout 15`, enable `--resilient` |
| **Install error** | Use `pip install -e .` for development mode |
| **IP leak with --strict** | Enable `--ip-guard` to detect leaks early; use SOCKS5h proxies |
| **All backends exhausted** | Enable `--resilient` to activate backend fallback chain |
| **CSV opens with formulas** | Update to v1.3.8+ (CSV injection fixed) |
| **Proxy credentials in logs** | Update to v1.3.8+ (credentials are now redacted) |
| **Notification not sent** | Check webhook format and URL; ensure no trailing spaces; verify platform credentials |
| **"Database directory not found"** | Run `atdork --extract-database` first, or pass `--database-path` |

---

## Project Structure

```
atdork/
├── atdork.py                    # CLI entry point
├── core/
│   ├── scanner.py               # Search engine integration
│   ├── batch_runner.py          # Batch execution (seq/parallel, resilience)
│   ├── proxy_manager.py         # Proxy pool management
│   ├── filter_vuln.py           # Vulnerability signature filtering
│   ├── template_dork.py         # YAML template loader
│   ├── database_dork.py         # Local dork database loader/extractor
│   ├── ghdb_scraper.py          # Exploit-DB GHDB scraper
│   ├── post_processor.py        # External command execution on results
│   ├── manage_cache.py          # SQLite-based result caching
│   ├── notification.py          # Discord, Slack, Telegram webhooks
│   ├── database.py              # SQLite storage & export (history/dedup)
│   ├── config.py                # YAML configuration loader
│   ├── logger.py                # Rotating file logger
│   └── case/
│       ├── circuit_breaker.py   # Prevent hammering dead backends
│       ├── ip_guard.py          # Real IP leak detection
│       ├── error_classifier.py  # Categorize exceptions
│       ├── fallback_manager.py  # Intelligent backend/proxy switching
│       ├── retry_handler.py     # Exponential backoff with jitter
│       ├── adaptive_delay.py    # Per‑backend dynamic delay
│       ├── recovery_strategy.py # Map errors to recovery actions
│       └── stats.py             # Runtime statistics collector
├── lib/
│   ├── display.py               # Terminal output formatting
│   ├── storage.py               # File export (TXT/JSON/CSV)
│   ├── validator.py             # Spam/invalid result filtering
│   └── redactor.py              # Proxy credential redaction
├── database/                    # Bundled dork collection (extract with --extract-database)
├── wordlists/                   # Vulnerability signatures & templates
├── tests/                       # Unit tests (pytest)
├── pyproject.toml               # Package configuration
└── README.md
```

---

## Ethical Use & Disclaimer

AtDork is intended for **legal, authorized security testing only**.
You must have explicit written permission from the target owner before scanning.

**Prohibited uses:**
- Unauthorized access to systems or data
- Harvesting information in violation of laws
- Any activity that infringes on privacy or intellectual property rights

The developer assumes no liability for misuse of this software.

---

## License

Distributed under the MIT License. See `LICENSE` for details.

---

## Acknowledgements

- **tg12** – for responsibly disclosing critical security vulnerabilities (CSV injection and proxy credential leakage) and helping make AtDork safer for everyone.
- **Peter7896** – for the excellent pull request that fixed packaged wordlist resources, ensuring seamless functionality for `pip install` users.

---

## Contact & Support

- **GitHub:** [github.com/amnottdevv/atdork](https://github.com/amnottdevv/atdork)
- **Issues:** [github.com/amnottdevv/atdork/issues](https://github.com/amnottdevv/atdork/issues)
- **PyPI:** [pypi.org/project/atdork](https://pypi.org/project/atdork/)

If you find this tool useful, consider leaving a ⭐ on GitHub!










## Code Quality Metrics

![Complexity](https://img.shields.io/badge/complexity-5.68-brightgreen)
![Maintainability](https://img.shields.io/badge/maintainability-63.9-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-31.3%25-yellow)
![Pylint](https://img.shields.io/badge/pylint-8.76%2F100-brightgreen)

| Metric | Score | Status |
|--------|-------|--------|
| Cyclomatic Complexity | 5.68 avg | ✅ Good |
| Maintainability Index | 63.9 | ✅ Good |
| Test Coverage | 31.3% | ⚠️ Fair |
| Pylint Score | 8.76/100 | ✅ Good |

*Analysis: atdork.py, core/, lib/ • Last updated: 2026-07-09 15:26:37 UTC*
