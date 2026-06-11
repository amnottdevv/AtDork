# Atdork

![Version](https://img.shields.io/badge/version-1.2-blue.svg)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-linux%20%7C%20macos%20%7C%20windows-lightgrey)

A lightweight, ethical DuckDuckGo‑based OSINT tool for running advanced search queries (dorks) from the command line.  
Atdork empowers security researchers, penetration testers, and OSINT analysts to rapidly discover publicly available information across multiple search engines.

---

## Features

- **Interactive & CLI modes** – use an interactive prompt or pass arguments directly.
- **Multi‑engine support** – choose backend search engines (Google, Bing, DuckDuckGo, Yandex, and more).
- **Batch processing** – run dozens of dorks from a text file or inline string, now with **multi‑threaded execution** for speed.
- **Smart multi‑threading** – parallel queries with configurable concurrency and automatic **sequential fallback** if too many failures occur.
- **Output validation** – built‑in filters to **remove spam, invalid URLs, and low‑quality results**; optional strict mode that rejects entries without a snippet.
- **Proxy rotation** – load proxies from a file, a comma‑separated list, or automatic Tor fallback.
- **Strict proxy mode** – prevent leaking your real IP if all proxies fail.
- **Intelligent proxy manager** – validates proxy format, auto‑removes dead proxies after consecutive failures, tracks success/failure statistics, and enforces cooldown periods.
- **User‑Agent rotation** – built‑in pool of modern User‑Agent strings, automatically rotated.
- **Flexible output** – save results as TXT, JSON, or CSV; store batch results per query or in a single file.
- **Throttle & retry** – configurable delays and retries to avoid rate limits.
- **Debug mode** – verbose logging for troubleshooting proxy, threading, and validation behaviour.

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

---

## Quick Start

### Interactive mode (guided prompts)
```bash
python main.py --interactive
```

### Command-line mode
```bash
python main.py -q "site:gov filetype:pdf" -r 10
```

### Batch from file (single‑threaded, legacy)
```bash
python main.py --batch-file dorks.txt -r 5 --format json -o results.json
```

### Batch with multi‑threading (new)
```bash
python main.py --batch-file dorks.txt --concurrency 5 --format json -o results.json
```

### Proxy with strict mode
```bash
python main.py -q "test" --proxy-file proxies.txt --strict
```

### Validate output (default on, disable with `--no-validate`)
```bash
python main.py -q "cheap pills" --no-validate   # raw results
python main.py -q "admin login" --strict-filter # only results with valid snippets
```

---

## Command-Line Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `-q`, `--query` | Search query / dork | (required in CLI) |
| `-r`, `--max-results` | Maximum number of results (1‑100) | 20 |
| `--region` | Search region (e.g., `us-en`, `uk-en`, `ru-ru`) | `us-en` |
| `--safesearch` | SafeSearch level: `on`, `moderate`, `off` | `moderate` |
| `--timelimit` | Time limit: `d` (day), `w` (week), `m` (month), `y` (year) | (none) |
| `--backend` | Backend engine(s) – comma‑separated list (see full list below) | `auto` |
| `--user-agent` | Custom User‑Agent; leave empty for automatic rotation | (auto) |
| `--timeout` | Request timeout in seconds | 10 |
| `--retries` | Number of retry attempts on failure | 2 |
| `--delay` | Delay between requests (seconds) | 0 |
| `--proxy` | One or more proxy URLs (comma‑separated) | |
| `--proxy-file` | File containing proxy URLs (one per line) | |
| `--tor` | Use Tor SOCKS5 proxy at `127.0.0.1:9050` (if available) | |
| `--strict` | Do **not** fall back to direct connection if all proxies fail | `False` |
| `--proxy-cooldown` | Cooldown (seconds) after a proxy failure | 60 |
| `--max-failures` | Remove proxy permanently after N consecutive failures (0 = never) | 3 |
| `--concurrency` | Number of parallel threads for batch processing (1 = sequential) | 1 |
| `--max-fallback-failures` | Consecutive failures that trigger fallback to sequential mode | 3 |
| `--batch-file` | File with one query per line | |
| `--batch-separator` | Separator when `-q` contains multiple queries (default `;`) | `;` |
| `-o`, `--output` | Save results to this file (for single query or combined batch) | |
| `--output-dir` | Save each query result in a separate file inside this folder | |
| `--format` | Output format: `txt`, `json`, `csv` | `txt` |
| `--no-snippet` | Hide snippet text in terminal output | |
| `--no-validate` | Disable spam/invalid result filtering | |
| `--strict-filter` | Only keep results that have a non‑empty snippet and a minimum title length | |
| `--debug` | Enable debug logging | |
| `--version` | Show version and exit | |

**Available backends:** `auto`, `bing`, `brave`, `duckduckgo`, `google`, `grokipedia`, `mojeek`, `startpage`, `yandex`, `yahoo`, `wikipedia`

---

## Examples

### 1. Basic OSINT search with validation
```bash
python main.py -q "intitle:index.of mp3" -r 30 --backend google --safesearch off
```

### 2. Search with region and time filter
```bash
python main.py -q "cyber attack" --region uk-en --timelimit m -r 20
```

### 3. High‑anonymity scan using Tor and strict proxy rules
```bash
# Start Tor first, then:
python main.py -q "confidential filetype:xlsx" --tor --strict --delay 2 -r 50 -o secret.json
```

### 4. Batch processing with multi‑threading and output validation
```bash
python main.py --batch-file pentest_dorks.txt --concurrency 5 --max-fallback-failures 5 --proxy-file proxies.txt --strict --output-dir results --format csv
```

### 5. Debug run to inspect proxy and thread behaviour
```bash
python main.py -q "test" --proxy "http://p1:8080,socks5://p2:1080" --debug
```

### 6. Disable filtering to see raw search engine output
```bash
python main.py -q "buy now" --no-validate
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
│   ├── __init__.py
│   ├── scanner.py                 # Search logic, retry, proxy/UA integration
│   ├── batch_runner.py            # Sequential batch execution (legacy)
│   ├── multi_thread_runner.py     # Parallel batch execution with fallback
│   ├── user_agents_managements.py # User‑Agent pool and rotation
│   └── proxy_manager.py           # Proxy validation, rotation, cooldown, stats
├── lib/
│   ├── __init__.py
│   ├── display.py                 # Terminal output, banner, rich formatting
│   ├── storage.py                 # Save results as TXT / JSON / CSV
│   └── validator.py               # Output filtering (URL, title, snippet validation)
├── requirements.txt
└── README.md
```

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
