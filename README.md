
# Atdork

![Version](https://img.shields.io/badge/version-1.3-blue.svg)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-linux%20%7C%20macos%20%7C%20windows-lightgrey)
[![CI](https://github.com/amnottdevv/atdork/actions/workflows/ci.yml/badge.svg)](https://github.com/amnottdevv/atdork/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/tests-114%20passed-brightgreen)](https://github.com/amnottdevv/atdork/actions)
![GitHub Clones](https://img.shields.io/badge/clones-985%2F14d-blue)
![GitHub Visitors](https://img.shields.io/badge/visitors-519%2F14d-brightgreen)

A lightweight, ethical DuckDuckGo-based OSINT tool for running advanced search queries (dorks) from the command line.  
Atdork helps security researchers, penetration testers, and OSINT analysts quickly discover publicly available information across multiple search engines.

**v1.3 introduces built‑in resilience, adaptive rate limiting, SQLite storage, and comprehensive logging — making it production‑ready.**

---

## Features

- **Interactive & CLI modes** – use an interactive prompt or pass arguments directly.
- **Multi‑engine support** – choose backend search engines (Google, Bing, DuckDuckGo, Startpage, Yandex, etc.).
- **Batch processing** – run dozens of dorks from a text file or inline string, now with **multi‑threaded execution** for speed.
- **Resilience engine** (`--resilient`) – circuit breaker, automatic backend fallback, and intelligent retry handling.
- **Adaptive rate limiter** (`--adaptive-delay`) – dynamic per‑backend delay that responds to rate‑limits and recovers automatically.
- **Output validation** – built‑in filters to **remove spam, invalid URLs, and low‑quality results**; optional strict mode.
- **Vulnerability filter** (`--filter-vuln`) – identify results matching platform‑specific signatures (e.g. WordPress, Joomla).
- **Proxy rotation** – load proxies from a file, comma‑separated list, or Tor fallback (now with `user:pass@host:port` support).
- **Strict proxy mode** – prevent leaking your real IP if all proxies fail.
- **Intelligent proxy manager** – validates format, auto‑removes dead proxies, tracks statistics.
- **SQLite database** – persistent storage of all queries and results with resume, history, deduplication, and export.
- **Rotating file logs** – timestamped, module‑aware log files with automatic rotation.
- **User‑Agent rotation** – built‑in pool of modern User‑Agent strings, automatically rotated.
- **Flexible output** – save results as TXT, JSON, or CSV; store batch results per query or in a single file.
- **YAML configuration** – store your favourite settings in `atdork.yaml` for reproducibility.
- **CI/CD pipeline** – automated tests, linting, and security scanning on every commit.

---

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/amnottdevv/atdork.git
   cd atdork
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

   Requirements:
   - `duckduckgo-search>=7.0`
   - `rich>=13.0`
   - `pyfiglet>=0.8`
   - `pyyaml>=6.0`

3. **(Optional) Tor**
   Install Tor if you plan to use the `--tor` flag. Atdork will automatically connect to `127.0.0.1:9050`.

---

## Quick Start

### Interactive mode (guided prompts)
```bash
python main.py --interactive
```

### Command‑line mode
```bash
python main.py -q "site:gov filetype:pdf" -r 10
```

### Batch from file (with resilience and rate limiter)
```bash
python main.py --batch-file dorks.txt --resilient --adaptive-delay -r 20 --format json -o results.json
```

### Proxy with strict mode (now with authentication)
```bash
python main.py -q "admin login" --proxy "http://user:pass@proxy:8080" --strict
```

### Filter vulnerable WordPress results
```bash
python main.py -q "inurl:wp-content" -r 30 --filter-vuln wordpress
```

---

## Command-Line Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--interactive` | Launch interactive mode | (off) |
| `-q`, `--query` | Search query / dork | |
| `-r`, `--max-results` | Maximum number of results (1‑100) | 20 |
| `--region` | Search region (e.g. `us-en`, `uk-en`) | `us-en` |
| `--safesearch` | `on`, `moderate`, `off` | `moderate` |
| `--timelimit` | `d` (day), `w` (week), `m` (month), `y` (year) | (none) |
| `--backend` | Backend engine(s) – comma‑separated | `auto` |
| `--user-agent` | Custom User‑Agent (auto‑rotate if empty) | (auto) |
| `--timeout` | Request timeout (seconds) | 10 |
| `--retries` | Number of retry attempts on failure | 2 |
| `--delay` | Delay between requests (seconds) | 0 |
| `--proxy` | One or more proxy URLs (comma‑separated) | |
| `--proxy-file` | File containing proxy URLs | |
| `--tor` | Use Tor SOCKS5 proxy | |
| `--strict` | Fail instead of falling back to direct connection | `False` |
| `--proxy-cooldown` | Cooldown after a proxy failure (seconds) | 60 |
| `--max-failures` | Remove proxy after N consecutive failures | 3 |
| `--resilient` | Enable resilience mode (circuit breaker + fallback) | `False` |
| `--adaptive-delay` | Enable adaptive rate limiting per backend | `False` |
| `--concurrency` | Number of parallel threads for batch | 1 |
| `--max-fallback-failures` | Consecutive failures before fallback to sequential | 3 |
| `--batch-file` | File with one query per line | |
| `--batch-separator` | Separator for inline multiple queries | `;` |
| `-o`, `--output` | Save results to file | |
| `--output-dir` | Save each query result as a separate file | |
| `--format` | Output format: `txt`, `json`, `csv` | `txt` |
| `--no-snippet` | Hide snippet text in terminal | |
| `--no-validate` | Disable spam/invalid result filtering | |
| `--strict-filter` | Stricter filter (require non‑empty snippet) | |
| `--filter-vuln` | Filter results by vulnerability platform (e.g. `wordpress`) | |
| `--db-path` | SQLite database path | `atdork.db` |
| `--resume` | Resume pending queries from the database | |
| `--history` | Show search history | |
| `--no-dedup` | Disable global URL deduplication | |
| `--export-db` | Export database to JSON/CSV | |
| `--log-file` | Log file path | `atdork.log` |
| `--no-fallback-backends` | Disable backend fallback | |
| `--no-verify` | Disable SSL verification (not recommended) | |
| `--debug` | Enable debug logging | |
| `--version` | Show version and exit | |

**Available backends:** `auto`, `bing`, `brave`, `duckduckgo`, `google`, `grokipedia`, `mojeek`, `startpage`, `yandex`, `yahoo`, `wikipedia`.

---

## Examples

### 1. Basic OSINT search with validation
```bash
python main.py -q "intitle:index.of mp3" -r 30 --backend google --safesearch off
```

### 2. High‑anonymity scan with Tor and strict proxy rules
```bash
python main.py -q "confidential filetype:xlsx" --tor --strict --delay 2 -r 50 -o secret.json
```

### 3. Batch processing with resilience and rate limiter
```bash
python main.py --batch-file pentest_dorks.txt --concurrency 5 --resilient --adaptive-delay --proxy-file proxies.txt --output-dir results --format csv
```

### 4. Resume an interrupted batch
```bash
python main.py --resume
```

### 5. Export all stored results
```bash
python main.py --export-db all_results.json
```

### 6. Debug run to inspect proxy and thread behaviour
```bash
python main.py -q "test" --proxy "http://user:pass@proxy:8080" --debug
```

### 7. Strict filtering for high‑quality OSINT reports
```bash
python main.py -q "financial report filetype:pdf" --strict-filter -o clean_results.json
```

---

## Project Structure

```
atdork/
├── main.py                        # Entry point, CLI argument parser, orchestration
├── core/
│   ├── case/
│   │   ├── resilience.py          # Circuit breaker, backend fallback
│   │   └── rate_limiter.py        # Adaptive per‑backend rate limiting
│   ├── scanner.py                 # Search logic, retry, proxy/UA integration
│   ├── batch_runner.py            # Batch execution (sequential/parallel)
│   ├── proxy_manager.py           # Proxy validation, rotation, statistics
│   ├── database.py                # SQLite storage and export
│   ├── logger.py                  # Rotating file + console logging
│   ├── filter_vuln.py             # Vulnerability signature filtering
│   └── config.py                  # YAML configuration loader
├── lib/
│   ├── display.py                 # Terminal output, banner
│   ├── storage.py                 # Save results as TXT / JSON / CSV
│   └── validator.py               # Output filtering (spam, URL validation)
├── tests/                         # 114 unit tests (pytest)
├── wordlists/                     # Vulnerability signature files
├── presets/                       # Dork templates (YAML)
├── .github/workflows/ci.yml       # CI pipeline
├── atdork.yaml                    # User configuration file
├── requirements.txt
└── README.md
```
## activitie graph
![Alt](https://repobeats.axiom.co/api/embed/34d4bf05a783d8e3ea0762148747c10ed8f53e9f.svg "Repobeats analytics image")
---

## Ethical Use & Disclaimer

Atdork is intended for **ethical and legal purposes only**, such as:
- Authorised penetration testing
- Security research
- OSINT investigations with proper consent
- Educational use

**Do not use this tool for:**
- Unauthorised access to systems or data
- Harvesting information in violation of laws or regulations
- Any activity that infringes on privacy or intellectual property rights

Always ensure you comply with applicable local and international laws. The developer assumes no liability for misuse of this software.

---

## Contributing

Pull requests, issues, and feature suggestions are welcome.  
Please open an issue first to discuss what you would like to change.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

Distributed under the MIT License. See `LICENSE` for more information.

---

## Contact

**alzzmarket**  
GitHub: [github.com/amnottdevv/atdork](https://github.com/amnottdevv/atdork)  

If you find this tool useful, consider leaving a ⭐ on the repository.
