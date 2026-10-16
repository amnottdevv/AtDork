# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# AtDork — containerized CLI
#
#   docker build -t atdork .
#   docker run --rm atdork --version
#   docker run --rm atdork search "exposed s3 bucket" --limit 10
#
# The image bundles the Atdork-DB dork database (baked at build time).
# Mount your own checkout to override, or an empty volume to bootstrap:
#
#   docker run --rm -v "$PWD/work":/work -v atdork-data:/opt/atdork-db atdork install @cve/cve_1.txt
# ---------------------------------------------------------------------------
FROM python:3.12-slim

LABEL org.opencontainers.image.title="AtDork" \
      org.opencontainers.image.description="OSINT dorking tool with multi-engine search, batch processing and a dork package manager" \
      org.opencontainers.image.source="https://github.com/amnottdevv/atdork" \
      org.opencontainers.image.licenses="MIT"

# git is required by the package manager (`atdork update`, first-run DB bootstrap)
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# non-root runtime user
RUN useradd --create-home --shell /bin/sh atdork

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir . \
    && rm -rf /root/.cache

# Bake the dork database (rebuild the image to refresh it, or mount your own)
ARG DB_REPO=https://github.com/amnottdevv/Atdork-DB
RUN git clone --depth 1 "$DB_REPO" /opt/atdork-db
ENV ATDORK_DB_REPO=/opt/atdork-db

# /work is the runtime workspace — mount your files there (-v "$PWD":/work)
RUN mkdir -p /work && chown -R atdork:atdork /opt/atdork-db /work
USER atdork
WORKDIR /work

COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/atdork-entry
ENTRYPOINT ["atdork-entry"]
CMD ["--help"]
