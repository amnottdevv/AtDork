# Installation Guide

AtDork requires **Python >= 3.9** and works seamlessly across **Linux (including
WSL), macOS, and Windows** — or no Python at all via Docker.

!!! tip "No local install? Use Docker"
    The official image ships the CLI **plus the full dork database**:

    ```bash
    docker pull ghcr.io/amnottdevv/atdork:latest
    docker run --rm -it ghcr.io/amnottdevv/atdork:latest -q "site:gov filetype:pdf"
    ```

    Full details — volumes, networking, compose — in [Docker](docker.md).

---

## 1. Installation via PyPI (Recommended)

The most direct and stable method to acquire AtDork is via the Python Package
Index:

```bash
pip install atdork
```

## 2. Installing From Source (Development Mode)

If you wish to test bleeding-edge features, inspect the code, or modify
internal wordlists, build it locally:

```bash
# Clone the repository
git clone https://github.com/amnottdevv/atdork.git
cd atdork

# Install using editable mode
pip install -e .
```

## 3. One-Time Data Setup — Clone Atdork-DB

Since v1.3.9.7 AtDork ships **code only**; the dork packages (~994,600 dorks
across 31 `@folders`) live in the
[Atdork-DB](https://github.com/amnottdevv/Atdork-DB) repository. The package
manager (`atdork search`, `atdork install`, `--database-dork`) reads a local
checkout. Clone it **once**:

```bash
git clone https://github.com/amnottdevv/Atdork-DB.git ~/Atdork-DB
```

AtDork discovers the checkout automatically in this order:

| Priority | Source | Example |
| :--- | :--- | :--- |
| 1 | `--db-repo` flag (per command) | `atdork search cve --db-repo /opt/Atdork-DB` |
| 2 | Environment variable | `export ATDORK_DB_REPO=~/Atdork-DB` |
| 3 | Config file (`db_repo`) | written by `--db-repo` + `--write` |
| 4 | `~/Atdork-DB` | default home checkout |
| 5 | Sibling of the AtDork checkout | `../Atdork-DB` |
| 6 | `./Atdork-DB` | current working directory |

Docker users can skip this entirely — the image bundles the database at
`/opt/atdork-db` (see [Docker](docker.md)).

## 4. Post-Installation Verification

Validate that the CLI entry point successfully mapped to your system's `PATH`
variables:

```bash
atdork --version
```

**Expected output:**

```text
atdork 1.3.9.7
```

Verify the database connection as well:

```bash
atdork index          # lists all 123 packages (ref | dorks | size | description)
atdork search cve     # filters that list by keyword
atdork installed      # lists packages copied into your local store (~/.atdork/packages)
```

---

## 5. Optional Dependencies

If you plan to utilize **Tor Integration**, ensure the `tor` service is
installed and running on your system before using the `--tor` flag.

```bash
sudo apt install tor     # Debian/Ubuntu
sudo systemctl start tor
```

## 6. Upgrading

```bash
pip install --upgrade atdork      # upgrade the CLI
atdork update                     # git pull the Atdork-DB checkout (refresh dorks)
```

---

## Next Steps

- [Quick Start](quickstart.md) — run your first searches in under a minute
- [Docker](docker.md) — containerized usage, volumes and compose
- [Dork Database](database/index.md) — browse packages + the
  [web catalog](https://amnottdevv.github.io/Atdork-DB/)
