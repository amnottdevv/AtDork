# Introduction to AtDork

Welcome to the official documentation for **AtDork**, a professional Open Source Intelligence (OSINT) and advanced dorking tool engineered for security researchers, penetration testers, and bug bounty hunters.

AtDork automates the extraction of exposed documents, vulnerable parameters, misconfigured server indexes, and leaked credentials from public search engine indexing.

---

## Why AtDork?

Unlike conventional dorking scripts that easily trigger captchas and face IP bans, AtDork incorporates sophisticated engineering principles to guarantee high availability and evasion:

- **Blazing Fast Parallelism** – Highly optimized multi-threaded processing with configurable concurrency limits.
- **Multi-Engine Aggregator** – Queries DuckDuckGo, Google, Bing, Startpage, Yandex, Yahoo, and more.
- **Ironclad Anonymity** – Native Tor integration, persistent proxy rotation pools, and `--ip-guard` to prevent identity leaks.
- **Intelligent Resilience** – Built-in circuit breakers, adaptive jitter delays, and error classification algorithms.
- **Seamless Pipelines** – Directly pipe discovered endpoints into vulnerability scanners like `wpscan` or `sqlmap`.
- **Template System** – YAML-based dork collections with `{target}` substitution and selective execution.

---

## Document Layout

To master AtDork, explore the documentation layout based on your skill level:

- **[Installation](installation.md)** – Standard setups via PyPI or local building from source code.
- **[Quick Start](quickstart.md)** – Run your first queries within 60 seconds.
- **[Basic Usage](basic-usage.md)** – Common commands and practical examples.
- **[Features](features/resilience-system.md)** – Deep dive into resilience, proxy, templates, and batch processing.
- **[CLI Reference](cli-reference.md)** – The full master matrix containing all 50+ configuration flags.
- **[Troubleshooting](troubleshooting.md)** – Common issues and how to resolve them.

---

## Quick Stats

- **50+ CLI Flags** – Complete control over every aspect of your search.
- **6+ Search Engines** – DuckDuckGo, Google, Bing, Startpage, Yandex, Yahoo.
- **114+ Unit Tests** – Production-ready stability and reliability.
- **10+ Templates** – Pre-built dork collections for SQLi, XSS, WordPress, and more.

!!! warning "Ethical Use"
    AtDork is intended for **legal, authorized security testing only**. You must have explicit written permission from the target owner before scanning. Unauthorized access to systems or data is strictly prohibited.

---

## Quick Navigation

| Section | Description |
| :--- | :--- |
| [Installation](installation.md) | Install via `pip install atdork` or build from source |
| [Quick Start](quickstart.md) | First search in under 60 seconds |
| [Basic Usage](basic-usage.md) | Common commands and examples |
| [Resilience System](features/resilience-system.md) | Circuit breakers, adaptive delays, and fallback |
| [Proxy & Anonymity](features/proxy-anonymity.md) | Proxy pools, Tor, strict mode, IP guard |
| [Vulnerability Filter](features/filter-vuln.md) | Platform detection with custom wordlists |
| [Template System](features/template-system.md) | YAML templates with `{target}` substitution |
| [Batch Processing](features/batch-processing.md) | Parallel execution and resume capability |
| [Output Formats](features/output-formats.md) | JSON, CSV, TXT, and SQLite |
| [CLI Reference](cli-reference.md) | Complete flag reference (50+ flags) |
| [Troubleshooting](troubleshooting.md) | Common issues and solutions |

---

## Get Started

Ready to start? Run your first search now:

```bash
atdork -q "site:gov filetype:pdf" -r 10
```

Or explore the [Quick Start](quickstart.md) guide for a step-by-step tutorial.
