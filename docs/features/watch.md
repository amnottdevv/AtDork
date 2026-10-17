# Watch Mode

Watch mode monitors dorks for you: register a **watch** (a name plus the dorks
to run), then run it as often as you like. Each run re-executes the dorks,
compares the result URLs against the saved history, and reports **only the new
findings** — on the console and, if configured, through your webhook
([Notification](notification.md): Discord, Slack, Telegram).

There is no daemon and no internal scheduler: one `atdork watch run` is exactly
one cycle, which makes it a natural cron/systemd-timer job.

```bash
# 1. register a watch (stored in the environment)
atdork watch add acme \
    --dork "site:acme.com ext:env" \
    --dork "site:acme.com intitle:index.of" \
    --notify discord:https://discord.com/api/webhooks/…

# 2. first run records a baseline (no "new" spam)
atdork watch run acme

# 3. every later run reports the delta only
atdork watch run acme
```

Put step 3 in cron (each environment keeps its own watch state):

```cron
0 */6 * * *  cd /home/me && atdork --env ~/AtDork-workflows/atdork-env \
             watch run acme >> ~/atdork-watch.log 2>&1
```

Use `atdork watch run --all` to run every saved watch in one cycle.

## Dork sources

A watch can combine three kinds of sources — they are resolved on every run,
so editing the file (or the Atdork-DB package) changes what is monitored
without touching the watch:

| Flag | Source |
| :--- | :--- |
| `--dork "…"` | A literal dork (repeatable) |
| `--batch-file dorks.txt` | A file of dorks, one per line (repeatable) |
| `--database-dork @ghdb/01_footholds` | A database dork package spec (`@folder/file`, `c@file.txt`, whole folders) |

```bash
atdork watch add exposed-env \
    --database-dork @ghdb/01_footholds \
    --batch-file extra-dorks.txt \
    --max-results 30 --region us-en
```

Re-running `watch add` for an existing name **merges**: new dorks/files are
appended, options and the webhook target are updated, and the seen-URL history
is kept — so you never get re-notified about old findings.

## Commands

| Command | Description |
| :--- | :--- |
| `atdork watch add <name> [sources] [--notify TARGET] [options]` | Create (or extend) a watch. |
| `atdork watch list` | List watches with their source summary and last run. |
| `atdork watch show <name>` | Show the definition, stored options, history counters and the last new URLs. |
| `atdork watch run <name>` | Run one cycle (cron-friendly). |
| `atdork watch run --all` | Run every watch. |
| `atdork watch remove <name>` | Delete the watch **and** its history. |

Stored search options (`--backend`, `--max-results`, `--timeout`, `--retries`,
`--delay`, `--region`, `--safesearch`, `--timelimit`) are written into the watch
on `watch add` (defaults come from your config) and can be overridden per run —
`atdork watch run acme --max-results 50` changes that cycle only.

Useful `run` flags:

| Flag | Effect |
| :--- | :--- |
| `--dry-run` | Resolve the dorks and exit — nothing is searched, no credits spent. |
| `--notify TARGET` | Override the stored webhook target for this cycle. |
| `--concurrency N` | Run N dorks in parallel. |
| `--all` | Run every watch and print a combined summary. |

## How findings are detected

* Every result's link is **normalized** before comparison: scheme/host are
  lowercased, `www.` is dropped, a trailing slash and URL fragments are
  ignored, and known tracking parameters (`utm_*`, `gclid`, `fbclid`, …) are
  removed. `http://WWW.Example.com/a/?utm_source=x` and
  `https://example.com/a` count as the same finding.
* The **first run** of a watch only records a baseline (and sends one short
  baseline notification, so you know the webhook works). Later runs report the
  delta.
* The history is capped at **10,000 URLs** per watch; the oldest entries are
  dropped first.
* Watch runs deliberately **never use the search cache** — a monitored dork
  must be re-fetched to notice changes.

## State and exit codes

State lives in `<env>/state/watch/<name>.json` (or
`~/.atdork/state/watch/<name>.json` without an environment) and holds both the
definition and the history — deleting the file resets the watch to a baseline
state.

| Exit code | Meaning |
| :--- | :--- |
| `0` | Cycle completed (new findings, none, or some dorks failed). |
| `1` | The watch is unknown/invalid, or **every** dork failed. |
| `2` | `watch run` without a name and without `--all`. |

Notification problems never fail a run: a dead webhook is logged and the cycle
still exits `0` (its findings are already saved in the history).
