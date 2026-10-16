#!/bin/sh
# AtDork container entrypoint.
#
# 1. If no dork database is present at $ATDORK_DB_REPO (first run with a
#    fresh/empty volume), clone it once — the clone persists in the volume.
# 2. Exec the CLI so signals reach atdork directly.
set -e

DB="${ATDORK_DB_REPO:-/opt/atdork-db}"

if [ ! -f "$DB/Index.idn" ]; then
  URL="${ATDORK_DB_URL:-https://github.com/amnottdevv/Atdork-DB}"
  echo "[atdork] no dork database at $DB — cloning $URL ..." >&2
  mkdir -p "$DB"
  git clone --depth 1 "$URL" "$DB"
fi

export ATDORK_DB_REPO="$DB"
exec atdork "$@"
