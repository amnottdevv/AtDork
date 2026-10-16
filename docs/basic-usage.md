# Basic Usage

This guide covers the most common AtDork commands you'll use daily. Whether
you're a security researcher, bug bounty hunter, or OSINT practitioner, these
examples will help you get started quickly.

All examples assume you have AtDork installed. If not, see
[Installation](installation.md).

---

## Your First Search

The simplest command — search for PDF files on government websites:

```bash
atdork -q "site:gov filetype:pdf" -r 10
```

- `-q` — your search query (dork)
- `-r 10` — return up to 10 results

---

## Common Use Cases

### 1. Find Exposed Documents

```bash
# PDF files on government sites
atdork -q "site:gov filetype:pdf" -r 20

# Excel files on educational sites
atdork -q "site:edu filetype:xls" -r 20

# Config files with passwords
atdork -q 'filetype:env "DB_PASSWORD"' -r 20
```

### 2. Find Exposed Panels & Logins

```bash
# Admin login pages
atdork -q "inurl:admin login" -r 20

# phpMyAdmin consoles
atdork -q "intitle:phpmyadmin inurl:index.php" -r 20
```

### 3. Find Open Directories

```bash
# Directory indexing
atdork -q 'intitle:"index of" "backup"' -r 20
```

---

## Output Formats

Write results to disk in the format that fits your pipeline:

```bash
# JSON — for programmatic processing
atdork -q "site:example.com" --format json -o results.json

# CSV — for spreadsheets
atdork -q "site:example.com" --format csv -o results.csv

# Plain text (default)
atdork -q "site:example.com" -o results.txt

# One file per query in a directory
atdork --batch-file dorks.txt --output-dir ./results
```

---

## Batch Processing

Feed a whole list of dorks at once — one per line:

```bash
cat > dorks.txt << 'EOF'
site:edu filetype:xls
inurl:admin login
intitle:"index of" "backup"
EOF

atdork --batch-file dorks.txt -r 20 --format json --output-dir ./out
```

Use `-v` to stream results to the terminal while the batch runs.

---

## Dork Packages (Atdork-DB)

Since v1.3.9.7 the dork data lives in the
[Atdork-DB](https://github.com/amnottdevv/Atdork-DB) repository — **123
packages across 31 `@folders`, ~994,600 dorks** — managed by the built-in
package manager. **[Browse the web catalog →](https://amnottdevv.github.io/Atdork-DB/)**

### Search the index

```bash
atdork search shodan         # packages mentioning "shodan"
atdork index                 # full package listing with descriptions
```

### Install packages

```bash
atdork install @cve/cve_1.txt     # canonical ref: folder + file
atdork install c@cve_1.txt        # shorthand (unique folder prefix)
atdork install @ghdb              # entire folder
atdork installed                  # list what's in ~/.atdork/packages
atdork uninstall @ghdb/01_footholds
```

### Run installed packages as queries

```bash
# Installed packages work as batch files
atdork --batch-file c@cve_1.txt -r 20

# Or load any ref straight from the database root (no install step)
atdork --database-dork @ghdb/01_footholds -r 20

# Preview without running
atdork --database-dork @cve --database-preview

# Random sample from a folder (deterministic with a seed)
atdork --database-dork @cms --database-r 50 --database-seed 7

# List everything available
atdork --list-database-dork
```

### Keep the data fresh

```bash
atdork update      # git pull --ff-only on the Atdork-DB checkout
```

Full ref grammar, folder list and category guides:
[Dork Database](database/index.md).

---

## Run with Docker

The official image bundles the CLI **and** the full database — no Python or
clone needed:

```bash
docker pull ghcr.io/amnottdevv/atdork:latest

# Search
docker run --rm -it ghcr.io/amnottdevv/atdork:latest -q "site:gov filetype:pdf" -r 10

# Batch with local files mounted
docker run --rm -it -v "$PWD:/data" -w /data ghcr.io/amnottdevv/atdork:latest \
  --batch-file dorks.txt --format json -o out.json

# Persist the package store between runs
docker volume create atdork-store
docker run --rm -it -v atdork-store:/home/atdork/.atdork \
  ghcr.io/amnottdevv/atdork:latest install @cve/cve_1.txt
```

Full details in [Docker](docker.md).

---

## Anonymity & Proxies

```bash
# Route through Tor (requires the tor service running)
atdork -q "site:example.com" --tor

# Custom proxy
atdork -q "site:example.com" --proxy http://127.0.0.1:8080

# Refuse to fall back to your real IP if the proxy dies
atdork -q "site:example.com" --proxy http://127.0.0.1:8080 --ip-guard
```

See [Proxy & Anonymity](features/proxy-anonymity.md) for rotation pools and
anonymity levels.

---

## Common Flag Reference

| Flag | Purpose |
| :--- | :--- |
| `-q`, `--query` | Main search query |
| `-r`, `--max-results` | Max results per engine (1–100) |
| `--batch-file` | File with one dork per line |
| `-o`, `--output` | Output file path |
| `--format` | `txt`, `json`, or `csv` |
| `--template` | Load a named dork template |
| `--target` | Domain for `{target}` substitution |
| `--database-dork` | Load dorks from an Atdork-DB ref |
| `--database-preview` | Preview loaded dorks without running |
| `--tor` / `--proxy` | Anonymize traffic |
| `--ip-guard` | Never fall back to your real IP |

Full list in [CLI Reference](cli-reference.md).

---

## Next Steps

- [CLI Reference](cli-reference.md) — every flag and subcommand
- [Batch Processing](features/batch-processing.md) — advanced batch workflows
- [Dork Database](database/index.md) — packages + web catalog
- [Docker](docker.md) — containerized usage
- [Troubleshooting](troubleshooting.md) — when something breaks
