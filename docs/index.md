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
- **Dork Package Manager** – `atdork search` / `install` / `update` over **994,600+ dorks** in [Atdork-DB](https://github.com/amnottdevv/Atdork-DB) — 123 dork packages across 31 `@folders`, plus 7 installable `@plugins/` tools — all browsable in the [web catalog](https://amnottdevv.github.io/Atdork-DB/).
- **Workflow Engine** – Sequential multi-step dork campaigns in YAML: threshold-triggered retries, worker pools, guarded outputs, resumable state (`atdork workflow run`, `--run-workflow`).
- **Plugin System** – Install extra Python tools from Atdork-DB (`atdork install @plugins/<tool>`); each surfaces as `--<plugin>-<option>` flags (`--dorkbuilder-text "…"`).
- **Docker Ready** – Official image `ghcr.io/amnottdevv/atdork` ships the CLI *and* the full database — zero setup ([Docker](docker.md)).

---

## Document Layout

To master AtDork, explore the documentation layout based on your skill level:

- **[Installation](installation.md)** – PyPI, source, Docker, and the one-time Atdork-DB setup.
- **[Quick Start](quickstart.md)** – Run your first queries within 60 seconds.
- **[Basic Usage](basic-usage.md)** – Common commands and practical examples.
- **[Docker](docker.md)** – Containerized usage, volumes, and compose.
- **[Dork Database](database/index.md)** – Packages, package manager, and the [web catalog](https://amnottdevv.github.io/Atdork-DB/).
- **[Features](features/resilience-system.md)** – Deep dive into resilience, proxy, templates, and batch processing.
- **[Environment](features/environment.md)** – Isolated workspaces: every result, log and cache file stays inside one root folder.
- **[Workflows](features/workflows.md)** – Sequential multi-step campaigns: thresholds, retries, workers, resume.
- **[Plugins](features/plugins.md)** – Installable tools exposed as `--<plugin>-<option>` flags.
- **[CLI Reference](cli-reference.md)** – The full master matrix containing all 50+ configuration flags.
- **[Configuration](configuration.md)** – The `atdork.yml` guide: layered files, sections, `${ENV}` interpolation.
- **[Engines & Providers](engines.md)** – Scraping engines plus Serper / SerpApi / Brave Search API providers.
- **[Troubleshooting](troubleshooting.md)** – Common issues and how to resolve them.

---

## Quick Stats

- **994,600+ Dorks** – Across 123 packages in 31 themed `@folders`, refreshed weekly ([web catalog](https://amnottdevv.github.io/Atdork-DB/)).
- **50+ CLI Flags** – Complete control over every aspect of your search.
- **6+ Search Engines** – DuckDuckGo, Google, Bing, Startpage, Yandex, Yahoo.
- **3 API Providers** – Serper.dev, SerpApi and Brave Search API via `engines:` in `atdork.yml`.
- **280+ Unit Tests** – Production-ready stability and reliability.
- **10+ Templates** – Pre-built dork collections for SQLi, XSS, WordPress, and more.

!!! warning "Ethical Use"
    AtDork is intended for **legal, authorized security testing only**. You must have explicit written permission from the target owner before scanning. Unauthorized access to systems or data is strictly prohibited.

---

## Quick Navigation

| Section | Description |
| :--- | :--- |
| [Installation](installation.md) | Install via `pip`, source, or Docker |
| [Docker](docker.md) | Containerized usage with the bundled database |
| [Quick Start](quickstart.md) | First search in under 60 seconds |
| [Basic Usage](basic-usage.md) | Common commands and examples |
| [Dork Database](database/index.md) | Package manager + [web catalog](https://amnottdevv.github.io/Atdork-DB/) |
| [Package Manager](features/package-manager.md) | `search` / `install` / `update` deep dive |
| [Environment](features/environment.md) | Isolated workspaces — nothing written outside the root |
| [Workflows](features/workflows.md) | Multi-step campaigns — `workflow run` / `--run-workflow` |
| [Plugins](features/plugins.md) | Installable tools — `--<plugin>-<option>` flag system |
| [Configuration](configuration.md) | `atdork.yml` v2: sections, layering, `${ENV}` interpolation |
| [Engines & Providers](engines.md) | Built-in engines + Serper / SerpApi / Brave API providers |
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
pip install atdork                          # install the CLI
git clone https://github.com/amnottdevv/Atdork-DB.git ~/Atdork-DB   # dork data (once)
atdork -q "site:gov filetype:pdf" -r 10     # first search
```

Or use Docker — no Python or clone needed:

```bash
docker run --rm -it ghcr.io/amnottdevv/atdork:latest -q "site:gov filetype:pdf" -r 10
```

Explore the [Quick Start](quickstart.md) guide for a step-by-step tutorial,
browse the dork packages in the
**[web catalog](https://amnottdevv.github.io/Atdork-DB/)**, or dive into the
[Dork Database](database/index.md) workflow.
