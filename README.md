
# AtDork – Professional OSINT Dorking Tool

![Version](https://img.shields.io/badge/version-1.3.3-blue.svg)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-linux%20%7C%20macos%20%7C%20windows-lightgrey)
![Tests](https://img.shields.io/badge/tests-114%20passed-brightgreen)
![Lines](https://img.shields.io/badge/total%20lines-9%2C383-orange)
![Visitors](https://img.shields.io/badge/visitors-519%2F14d-brightgreen)
![Clones](https://img.shields.io/badge/clones-985%2F14d-blue)
![PyPI Downloads](https://img.shields.io/pypi/dm/atdork?color=blue)

**AtDork** is a powerful, ethical OSINT tool that performs advanced search queries (Google Dorks) across multiple search engines simultaneously. Designed for security researchers, penetration testers, and bug bounty hunters, it automates the discovery of exposed documents, vulnerable parameters, misconfigured servers, and other sensitive information available on the public web.

---

## Why AtDork?

- 🚀 **Blazing fast** – Multi‑threaded batch processing with configurable concurrency.
- 🔍 **Multi‑engine** – Queries DuckDuckGo, Google, Bing, Startpage, Yandex, Yahoo, and more.
- 🛡️ **Anonymous** – Built‑in proxy rotation, Tor integration, strict mode to prevent IP leaks.
- 🧹 **Clean results** – Automatic spam filtering, URL validation, and deduplication.
- 📊 **Professional output** – Export to JSON, CSV, TXT; SQLite database for history and resume.
- 🎯 **Smart filtering** – Vulnerability signature detection for WordPress, Joomla, SQLi, and more.
- 📝 **Template system** – Curated YAML‑based dork collections for instant productivity.
- ⚙️ **Highly configurable** – 47 CLI flags to control every aspect of your search.

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
# Output: atdork 1.3.3
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

### Database & History
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

### Advanced Options
```bash
# Custom User‑Agent
atdork -q "test" --user-agent "MyBot/1.0"

# Disable SSL verification (not recommended)
atdork -q "test" --no-verify

# Disable backend fallback
atdork -q "test" --no-fallback-backends

# Debug mode (verbose logging)
atdork -q "test" --debug

# Custom log file
atdork -q "test" --log-file my_scan.log

# Show results during batch
atdork --batch-file dorks.txt -v
```

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
| `--db-path` | Database path | `atdork.db` |
| `--resume` | Resume pending queries | |
| `--history` | Show search history | |
| `--no-dedup` | Disable URL deduplication | |
| `--export-db` | Export database to file | |
| `--config` | YAML config file path | |
| `--interactive` | Interactive mode | |
| `--debug` | Enable debug logging | |
| `--version` | Show version and exit | |

---

## Real‑World Use Cases

### Bug Bounty Reconnaissance
```bash
atdork --template sqli,xss,lfi --target target.com --proxy-file proxies.txt --strict --format json -o recon.json
```

### Exposed Database Credentials
```bash
atdork -q 'filetype:env "DB_PASSWORD"' -r 50 --no-validate -v
```

### Finding Admin Panels
```bash
atdork -q 'intitle:"admin panel" inurl:login' -r 30 --backend google --region uk-en
```

### WordPress Vulnerability Scanning
```bash
atdork -q "inurl:wp-content site:example.com" -r 40 --filter-vuln wordpress -v
```

### Automated Weekly Monitoring
```bash
# Add to crontab (Linux/macOS)
0 6 * * 1 cd /path/to/atdork && atdork --batch-file weekly_dorks.txt --format csv --output-dir /reports/$(date +\%Y-\%W)/
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
```

AtDork automatically loads this file from the current directory. CLI flags override YAML values.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **Rate limited (429)** | Add `--delay 3`, use `--proxy-file`, or enable `--adaptive-delay` |
| **No results** | Try different `--backend` (e.g., `startpage`, `yandex`) or `--region` |
| **Proxy fails** | Check format: `scheme://user:pass@host:port` |
| **Batch stuck** | Reduce `--concurrency`, add `--timeout 15` |
| **Install error** | Use `pip install -e .` for development mode |

---

## Project Structure

```
atdork/
├── atdork.py                    # CLI entry point
├── core/
│   ├── scanner.py               # Search engine integration
│   ├── batch_runner.py          # Sequential & parallel batch execution
│   ├── proxy_manager.py         # Proxy pool management
│   ├── filter_vuln.py           # Vulnerability signature filtering
│   ├── template_dork.py         # YAML template loader
│   ├── database.py              # SQLite storage & export
│   ├── config.py                # YAML configuration loader
│   ├── logger.py                # Rotating file logger
│   └── case/
│       ├── resilience.py        # Circuit breaker & fallback
│       └── rate_limiter.py      # Adaptive rate limiting
├── lib/
│   ├── display.py               # Terminal output formatting
│   ├── storage.py               # File export (TXT/JSON/CSV)
│   └── validator.py             # Spam/invalid result filtering
├── wordlists/                   # Vulnerability signatures & templates
├── tests/                       # 114 unit tests (pytest)
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

## Contact & Support

- **GitHub:** [github.com/amnottdevv/atdork](https://github.com/amnottdevv/atdork)
- **Issues:** [github.com/amnottdevv/atdork/issues](https://github.com/amnottdevv/atdork/issues)
- **PyPI:** [pypi.org/project/atdork](https://pypi.org/project/atdork/)

If you find this tool useful, consider leaving a ⭐ on GitHub!
```
