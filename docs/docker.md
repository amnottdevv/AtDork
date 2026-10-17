# Docker

Run AtDork in a container — no local Python required. The image bundles the
CLI, its dependencies and a baked copy of the
[Atdork-DB](https://github.com/amnottdevv/Atdork-DB) dork database, and runs
as a non-root user (`atdork`).

## Get the image

```bash
# published image (built & smoke-tested by CI on every push)
docker pull ghcr.io/amnottdevv/atdork:latest

# or build it from source
git clone https://github.com/amnottdevv/atdork.git
cd atdork
docker build -t atdork .
```

Version-pinned images are published for every release tag
(`ghcr.io/amnottdevv/atdork:1.5.0`), plus `latest` on every push to
`master`.

## Quick start

```bash
alias atdork='docker run --rm -it -v "$PWD":/work ghcr.io/amnottdevv/atdork:latest'

atdork --version
atdork search "exposed s3 bucket" --limit 10
atdork --batch-file dorks.txt -r 20
```

`/work` is the container's working directory — mount your current directory
so input files (`--batch-file`, `--output`) and results are visible on the host.

## Dork database

The Atdork-DB checkout is baked into the image at `/opt/atdork-db` (selected
via the `ATDORK_DB_REPO` environment variable). To keep installed packages
and a fresh database **between runs**, add a named volume:

```bash
docker volume create atdork-data

docker run --rm -v atdork-data:/opt/atdork-db ghcr.io/amnottdevv/atdork:latest index
docker run --rm -v atdork-data:/opt/atdork-db ghcr.io/amnottdevv/atdork:latest install @cve/cve_1.txt
docker run --rm -v atdork-data:/opt/atdork-db ghcr.io/amnottdevv/atdork:latest installed
```

If the mounted directory is empty, the entrypoint clones the database
automatically on first run. To use your own checkout instead:

```bash
docker run --rm -v "$HOME/Atdork-DB":/opt/atdork-db ghcr.io/amnottdevv/atdork:latest search cve
```

To refresh the baked database of a locally built image, just rebuild
(`docker build -t atdork .`) — the clone step always fetches `main`.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `ATDORK_DB_REPO` | `/opt/atdork-db` | Root of the Atdork-DB checkout the package manager reads |
| `ATDORK_DB_URL` | `https://github.com/amnottdevv/Atdork-DB` | Repository cloned by the entrypoint when the database is missing |

## Recipes

### Interactive shell inside the container

```bash
docker run --rm -it --entrypoint sh ghcr.io/amnottdevv/atdork:latest
```

### GHDB scrape into a persistent store

```bash
docker run --rm -v "$PWD":/work -v atdork-data:/opt/atdork-db \
  ghcr.io/amnottdevv/atdork:latest --ghdb-scrape "exposed passwords" \
  --ghdb-after 2024-01-01 --output results.json
```

### docker compose

```yaml
services:
  atdork:
    image: ghcr.io/amnottdevv/atdork:latest
    volumes:
      - ./work:/work
      - atdork-data:/opt/atdork-db
volumes:
  atdork-data:
```

```bash
docker compose run --rm atdork search cve --limit 5
```

## Image details

- Base: `python:3.12-slim` (Debian), CLI installed with `pip install .`
- Runtime user: `atdork` (non-root, uid auto) — mount with matching
  permissions for files you need to write on the host
- `git` is included so `atdork update` and the first-run database bootstrap work
- CI (`.github/workflows/docker-publish.yml`) builds the image and runs
  smoke tests (`--version`, `index`, `search`, `install`/`installed`,
  fresh-volume bootstrap) before publishing to GHCR on every push and tag
