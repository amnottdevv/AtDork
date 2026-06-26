# CLI Reference

Complete reference for all command-line arguments available in AtDork.

---

## Quick Overview

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `-q`, `--query` | String | None | Main search query (dork) |
| `-r`, `--max-results` | Integer | `20` | Max results per engine (1-100) |
| `--batch-file` | Path | None | File with one dork per line |
| `--batch-separator` | String | `;` | Separator for inline multiple queries |
| `-o`, `--output` | Path | None | Output file path |
| `--output-dir` | Path | None | Output directory for per-query files |
| `--format` | Choice | `txt` | Output format: `txt`, `json`, `csv` |
| `-v`, `--verbose` | Boolean | `false` | Show results during batch mode |
| `--no-snippet` | Boolean | `false` | Hide snippets in terminal output |
| `--template` | String | None | Template name(s), comma-separated |
| `--target` | String | None | Domain for `{target}` substitution |
| `--select` | String | None | Select specific dorks from template (e.g., `1,3,5`) |
| `--list-templates` | Boolean | `false` | List all available templates |
| `--template-path` | Path | None | Custom template directory |
| `--preview` | Boolean | `false` | Preview template dorks without executing |
| `--region` | Choice | `us-en` | Search region |
| `--safesearch` | Choice | `moderate` | SafeSearch level: `on`, `moderate`, `off` |
| `--timelimit` | Choice | None | Time filter: `d`, `w`, `m`, `y` |
| `--backend` | String | `auto` | Search engine(s), comma-separated |
| `--user-agent` | String | None | Custom User-Agent (auto-rotate if None) |
| `--timeout` | Integer | `10` | Request timeout in seconds |
| `--retries` | Integer | `2` | Retry attempts on failure |
| `--delay` | Float | `0` | Delay between requests (seconds) |
| `--proxy` | String | None | Comma-separated proxy URLs |
| `--proxy-file` | Path | None | File with proxy URLs (one per line) |
| `--tor` | Boolean | `false` | Use Tor SOCKS5 proxy |
| `--strict` | Boolean | `false` | Fail if all proxies are down (no direct fallback) |
| `--proxy-cooldown` | Integer | `60` | Cooldown after proxy failure (seconds) |
| `--max-failures` | Integer | `3` | Remove proxy after N consecutive failures |
| `--concurrency` | Integer | `1` | Number of parallel threads (1-10) |
| `--max-fallback-failures` | Integer | `3` | Failures before fallback to sequential |
| `--resilient` | Boolean | `false` | Enable circuit breaker & backend fallback |
| `--adaptive-delay` | Boolean | `false` | Enable adaptive rate limiting |
| `--ip-guard` | Boolean | `false` | Enable IP leak detection (requires `--strict`) |
| `--exec` | String | None | Execute command on each result (`{}` = URL) |
| `--exec-on-vuln` | String | None | Execute command only on vulnerable results |
| `--exec-parallel` | Integer | `1` | Parallel processes for `--exec` |
| `--exec-timeout` | Integer | `30` | Timeout per `--exec` command (seconds) |
| `--no-validate` | Boolean | `false` | Disable all spam/invalid filtering |
| `--strict-filter` | Boolean | `false` | Strict validation (title≥5, desc≥10) |
| `--validate-url` | Choice | `all` | URL mode: `only`, `path`, `params`, `all`, `false` |
| `--validate-title` | String | `5` | Min title length or `false` to disable |
| `--validate-desc` | String | `10` | Min description length or `false` to disable |
| `--validate-spam` | Boolean | `true` | Enable spam detection |
| `--filter-vuln` | String | None | Vulnerability platform filter |
| `--no-fallback-backends` | Boolean | `false` | Disable backend fallback |
| `--no-verify` | Boolean | `false` | Disable SSL certificate verification |
| `--log-file` | Path | `atdork.log` | Log file path |
| `--db-path` | Path | `atdork.db` | SQLite database path |
| `--resume` | Boolean | `false` | Resume pending queries from database |
| `--history` | Boolean | `false` | Show search history |
| `--no-dedup` | Boolean | `false` | Disable URL deduplication |
| `--export-db` | Path | None | Export database to file (json/csv) |
| `--config` | Path | None | YAML config file path |
| `--interactive` | Boolean | `false` | Run interactive mode |
| `--debug` | Boolean | `false` | Enable debug logging |
| `--version` | None | None | Show version and exit |
| `-h`, `--help` | None | None | Show help message and exit |

---

## Detailed Flag Descriptions

### Query & Results

| Flag | Description |
| :--- | :--- |
| `-q, --query` | Main search query (dork). Can be combined with `--batch-separator` for multiple queries. |
| `-r, --max-results` | Maximum number of results to return per query. Values above 100 are automatically clamped. |
| `--batch-file` | Path to a text file containing one dork per line. Lines starting with `#` are ignored. |
| `--batch-separator` | Separator for splitting a single `-q` string into multiple queries. Default is `;`. |

---

### Output Options

| Flag | Description |
| :--- | :--- |
| `-o, --output` | Save all results to a single file. Format determined by `--format` or file extension. |
| `--output-dir` | Save each query's results to a separate file in the specified directory. |
| `--format` | Output format: `txt` (human-readable), `json` (structured), `csv` (spreadsheet). |
| `-v, --verbose` | Display results in real-time during batch processing. |
| `--no-snippet` | Hide result snippets in terminal output for cleaner display. |

---

### Templates

| Flag | Description |
| :--- | :--- |
| `--template` | Load one or more YAML templates (comma-separated). Example: `--template sqli,wordpress` |
| `--target` | Domain to substitute for `{target}` placeholder in template dorks. |
| `--select` | Run only specific dorks from a template (1-based indices). Example: `--select 1,3,5` |
| `--list-templates` | Display all available templates with descriptions. |
| `--template-path` | Custom directory to search for template files. |
| `--preview` | Show template dorks without executing them. Useful for validation. |

---

### Search Engine Settings

| Flag | Description |
| :--- | :--- |
| `--region` | Search region/language code. Examples: `us-en`, `uk-en`, `de-de`, `ru-ru`. |
| `--safesearch` | Filter adult content: `on` (strict), `moderate` (default), `off` (none). |
| `--timelimit` | Restrict results by time: `d` (day), `w` (week), `m` (month), `y` (year). |
| `--backend` | Search engine(s) to use. Options: `google`, `bing`, `duckduckgo`, `startpage`, `yandex`, `auto`, or comma-separated list. |

---

### Request Tuning

| Flag | Description |
| :--- | :--- |
| `--user-agent` | Custom User-Agent string. If not provided, AtDork rotates through a built-in pool. |
| `--timeout` | Request timeout in seconds. Increases progressively with retries. |
| `--retries` | Number of retry attempts per backend before moving to the next. |
| `--delay` | Fixed delay between requests in seconds. Overridden by `--adaptive-delay` if enabled. |

---

### Proxy & Anonymity

| Flag | Description |
| :--- | :--- |
| `--proxy` | Comma-separated list of proxy URLs. Format: `scheme://[user:pass@]host:port`. |
| `--proxy-file` | Path to a file containing proxy URLs (one per line). Lines starting with `#` are ignored. |
| `--tor` | Enable Tor SOCKS5 proxy at `socks5h://127.0.0.1:9050`. |
| `--strict` | **Fail closed** – if all proxies fail, AtDork exits with error instead of falling back to direct connection. |
| `--proxy-cooldown` | Seconds to wait before retrying a failed proxy (default: 60). |
| `--max-failures` | Number of consecutive failures before a proxy is permanently removed (default: 3). |
| `--ip-guard` | Enable IP leak detection. Requires `--strict`. AtDork stops if your real IP is exposed. |

---

### Concurrency & Resilience

| Flag | Description |
| :--- | :--- |
| `--concurrency` | Number of parallel threads for batch processing (1-10). Higher values = faster but more likely to hit rate limits. |
| `--max-fallback-failures` | Consecutive failures before falling back from parallel to sequential mode. |
| `--resilient` | Enable intelligent fault-tolerance: circuit breaker, backend fallback, and automatic retry. |
| `--adaptive-delay` | Dynamically adjust request delay based on real-time backend response codes. |

---

### Post-Processing

| Flag | Description |
| :--- | :--- |
| `--exec` | Execute a shell command on each result URL. Use `{}` as placeholder for the URL. Example: `--exec "curl -I {}"` |
| `--exec-on-vuln` | Execute command only on results flagged as vulnerable by `--filter-vuln`. |
| `--exec-parallel` | Number of parallel processes for `--exec` commands. Default: 1. |
| `--exec-timeout` | Timeout in seconds for each `--exec` command. Default: 30. |

---

### Validation & Filtering

| Flag | Description |
| :--- | :--- |
| `--no-validate` | Disable all spam/invalid result filtering. Keeps raw results. |
| `--strict-filter` | Enable strict validation: title ≥ 5 chars, description ≥ 10 chars, spam detection on, URL all mode. |
| `--validate-url` | URL validation mode: `only` (domain only), `path` (domain+path), `params` (domain+params), `all` (full), `false` (disabled). |
| `--validate-title` | Minimum title length. Set to `false` to disable title validation. |
| `--validate-desc` | Minimum description length. Set to `false` to disable description validation. |
| `--validate-spam` | Enable/disable spam detection. Default: `true`. |
| `--filter-vuln` | Filter results by vulnerability platform. Examples: `wordpress`, `joomla`, `sqli`, `wordpress-link`. |

---

### Database & History

| Flag | Description |
| :--- | :--- |
| `--db-path` | Path to SQLite database file. Default: `atdork.db`. |
| `--resume` | Resume pending or failed queries from the database. |
| `--history` | Display search history with query text and status. |
| `--no-dedup` | Disable global URL deduplication. Keeps all results. |
| `--export-db` | Export entire database to JSON or CSV. Example: `--export-db all_results.json` |

---

### Logging & Debugging

| Flag | Description |
| :--- | :--- |
| `--log-file` | Path to log file. Default: `atdork.log`. |
| `--debug` | Enable debug logging (more verbose output). |
| `--no-verify` | Disable SSL certificate verification (not recommended). |
| `--no-fallback-backends` | Disable automatic backend fallback on failure. |

---

### Configuration & Mode

| Flag | Description |
| :--- | :--- |
| `--config` | Path to YAML configuration file. CLI flags override YAML values. |
| `--interactive` | Launch interactive mode with prompts instead of CLI flags. |
| `--version` | Display version and exit. |
| `-h, --help` | Display help message and exit. |

---

## Flag Categories

### By Purpose

| Category | Flags |
| :--- | :--- |
| **Core** | `-q`, `-r`, `--batch-file`, `--template`, `--interactive` |
| **Output** | `-o`, `--output-dir`, `--format`, `-v`, `--no-snippet` |
| **Search** | `--region`, `--safesearch`, `--timelimit`, `--backend` |
| **Network** | `--user-agent`, `--timeout`, `--retries`, `--delay`, `--no-verify` |
| **Proxy** | `--proxy`, `--proxy-file`, `--tor`, `--strict`, `--proxy-cooldown`, `--max-failures`, `--ip-guard` |
| **Resilience** | `--resilient`, `--adaptive-delay`, `--concurrency`, `--max-fallback-failures`, `--no-fallback-backends` |
| **Filter** | `--filter-vuln`, `--no-validate`, `--strict-filter`, `--validate-url`, `--validate-title`, `--validate-desc`, `--validate-spam` |
| **Post-Process** | `--exec`, `--exec-on-vuln`, `--exec-parallel`, `--exec-timeout` |
| **Database** | `--db-path`, `--resume`, `--history`, `--no-dedup`, `--export-db` |
| **Template** | `--template`, `--target`, `--select`, `--list-templates`, `--template-path`, `--preview` |
| **Debug** | `--log-file`, `--debug`, `--config` |
| **Info** | `--version`, `-h` |
