# Quick Start Guide

Get up and running with AtDork in less than a minute. These fundamental
workflows illustrate how to structure passive target reconnaissance.

---

## 1. Execute a Standard Search Query

Discover exposed PDF archives hosted on public government domains. By default,
AtDork targets `20` maximum entries using the optimal available engine
backend.

```bash
atdork -q "site:gov filetype:pdf" -r 10
```

## 2. Storing Extracted Data to Disk

Save search index outputs straight to a cleanly parsed JSON payload file for
upstream analysis:

```bash
atdork -q "intitle:index.of mp3" -r 20 --format json -o music.json
```

## 3. High-Throughput Batch Processing

Execute dozens of complex dorking patterns simultaneously.

1. Create a plain text payload containing one dork profile per line, named
   `dorks.txt`:

   ```text
   site:edu filetype:xls
   inurl:admin login
   intitle:"index of" "backup"
   ```

2. Pass the text map straight into the batch engine:

   ```bash
   atdork --batch-file dorks.txt -r 20
   ```

## 4. Use the Dork Database (Packages)

AtDork ships code only — the ~994,600 dorks live in
[Atdork-DB](https://github.com/amnottdevv/Atdork-DB), managed like a package
registry. **[Browse the web catalog](https://amnottdevv.github.io/Atdork-DB/)**
to explore packages, then install and run them:

```bash
# One-time: clone the data repo (skip if you use Docker — the image bundles it)
git clone https://github.com/amnottdevv/Atdork-DB.git ~/Atdork-DB

atdork search cve                # find packages by keyword
atdork install @cve/cve_1.txt    # install a package into ~/.atdork/packages
atdork --batch-file c@cve_1.txt -r 20   # run the installed package

# Or load straight from the database root, no install step:
atdork --database-dork @ghdb/01_footholds --database-preview   # show, don't run
atdork --database-dork @lfi -r 20                              # random sample run
```

Full workflow, ref grammar and the complete folder list:
[Dork Database](database/index.md).

## 5. Run with Docker (No Python Required)

The official image bundles the CLI **and** the full database:

```bash
docker pull ghcr.io/amnottdevv/atdork:latest

# Simple search
docker run --rm -it ghcr.io/amnottdevv/atdork:latest -q "site:gov filetype:pdf" -r 10

# Batch run with a local file mounted
docker run --rm -it -v "$PWD:/data" -w /data ghcr.io/amnottdevv/atdork:latest \
  --batch-file dorks.txt -r 20
```

Details — persistent package store, compose, custom DB — in
[Docker](docker.md).

## 6. Anonymize Traffic via Proxy

Route every request through a proxy chain (requires Tor for `--tor`):

```bash
atdork -q "site:example.com" --tor
atdork -q "site:example.com" --proxy http://127.0.0.1:8080 --ip-guard
```

---

## Next Steps

- [Basic Usage](basic-usage.md) — the complete daily-driver cookbook
- [CLI Reference](cli-reference.md) — every flag and subcommand
- [Dork Database](database/index.md) — packages + web catalog
- [Docker](docker.md) — containerized usage
