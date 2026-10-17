# Workflows

**Workflows** turn AtDork from a single-search CLI into an orchestration tool:
a workflow is a named, structured YAML definition that runs a series of dork
steps **strictly in order** — AtDork finishes one command before moving to the
next, exactly like chaining commands by hand, but with threshold retries,
worker concurrency, guarded outputs, and resumable state.

```yaml
workflows:
  recon-acme:
    target: "example.com"
    workers: 2
    steps:
      - name: exposed-files
        query: 'site:{target} ext:(pdf|docx) (intitle:index OR intitle:download)'
        when_results_below: 5
        retry_with:
          - 'site:{target} ext:pdf'
      - name: login-portals
        query: 'site:{target} inurl:(login OR signin)'
```

```bash
atdork workflow list                     # what's defined?
atdork workflow validate                 # schema check, zero API credits
atdork workflow run recon-acme           # execute
atdork --run-workflow .                  # one-shot: run the single workflow in the root
```

---

## Where definitions live

Workflow definitions are merged by name from (later wins):

1. **`workflows:`** in any [configuration](../configuration.md) layer
   (global `~/.config/atdork/config.yml`, working-dir `atdork.yaml`, the
   active environment config, or `--config`);
2. **explicit files** via `--file` / `--workflow-file` (repeatable);
3. **auto-discovered files** named `workflow.yaml`, `workflow.yml`,
   `workflows.yaml`, `workflows.yml`, `atdork-workflow.yaml` or
   `atdork-workflow.yml` in the **active environment root** and the **current
   working directory** ("root"). The environment root wins on name
   collisions, mirroring the config layer order (env > CWD).

A standalone file uses the same shape as the config section:

```yaml
version: 2
workflows:
  my-campaign:
    description: "..."        # shown by `workflow list`
    target: "example.com"
    steps:
      - name: first
        query: 'site:{target} inurl:login'
```

See [`examples/workflows/recon.yml`](https://github.com/amnottdevv/AtDork/blob/master/examples/workflows/recon.yml)
for a fully commented example and the repository-root `workflow.yaml` demo.

---

## CLI

### `atdork workflow list`

Every workflow from the merged sources with its step count, source
(`config` or file path) and description.

### `atdork workflow validate [name]`

Deep validation without spending a single request: schema, unknown keys,
step names, substitution tokens, threshold/retry pairing, output formats,
and whether every `{target}` usage has a target available. Exit code `1` on
errors — safe for CI.

```text
✗ broken — valid? no:
    workflows.broken.steps[0]: requires 'query' or 'queries'
    workflows.broken.steps[1].outputs[0]: format must be one of: csv, json, txt
```

### `atdork workflow run <name>`

`<name>` accepts three forms:

| Form | Meaning |
| :--- | :--- |
| `recon-acme` | Workflow name from config or a discovered file. |
| `./my-workflow.yml` | File path — runs when the file holds exactly one workflow. |
| `.` | The **single** workflow discovered in the current root (error listing choices if there are several). |

| Flag | Description |
| :--- | :--- |
| `--file FILE` | Additional workflow YAML file(s), repeatable. |
| `--target TARGET` | Override the workflow-level target. |
| `--workers N` | Override the worker (thread) count of every step. |
| `--step NAME` | Run only this step. |
| `--resume` | Skip steps already recorded as completed. |
| `--dry-run` | Print the fully resolved queries; no search, no state written. |

### One-shot main flags

The same engine is reachable without the subcommand:

```bash
atdork --run-workflow recon-acme --workflow-target example.org --workflow-workers 2
atdork --run-workflow . --workflow-dry-run
atdork --run-workflow recon-acme --workflow-resume
```

| Flag | Description |
| :--- | :--- |
| `--run-workflow NAME` | Workflow name, file path, or `.` (single workflow in the root). |
| `--workflow-file FILE` | Read definitions from this file. |
| `--workflow-target TARGET` | Override the target. |
| `--workflow-workers N` | Override the worker count. |
| `--workflow-resume` | Resume a previous run. |
| `--workflow-dry-run` | Resolve and print without searching. |

---

## Reference

### Workflow-level keys

| Key | Type | Description |
| :--- | :--- | :--- |
| `description` | string | Shown by `workflow list`. |
| `target` | string | Default target for `{target}` substitution (overridden by `--target`). |
| `workers` | int 1–64 | Threads **inside** each step; steps themselves stay sequential. Default `1`. |
| `steps` | list | The step definitions, executed in order. |
| `on_error` | `stop` \| `continue` | Default failure policy for all steps. Default `stop`. |
| `worker_overrides` | mapping | Search kwargs merged on top of every step's kwargs (see below). |
| *search keys* | | Workflow-wide defaults for any step search kwarg: `backend`, `max_results`, `region`, `safesearch`, `timelimit`, `timeout`, `retries`, `delay`, `user_agent`, `verify`, `fallback_backends`, `fallback_chain`, `forced_proxy`. |

### Step keys

| Key | Type | Description |
| :--- | :--- | :--- |
| `name` | string | Unique per workflow; defaults to `step-1`, `step-2`, ... |
| `query` | string | The dork to run (mutually exclusive with `queries`). |
| `queries` | list | Several dorks in one step — distributed across `workers`. |
| `when_results_below` | int | Threshold: fewer **unique** results → run `retry_with`. |
| `retry_with` | list | Alternate queries executed when the threshold is missed; their results are merged and deduplicated into the step results. |
| `on_error` | `stop` \| `continue` | Overrides the workflow-level policy for this step. |
| `outputs` | list | Result files: `- file: path.json` + optional `format: txt\|json\|csv`. |
| `worker_overrides` | mapping | Search kwargs applied on top for this step. |
| *search keys* | | Any workflow-level search key, overridden for this step. |

**Search kwargs precedence:** workflow defaults → step keys →
`worker_overrides` (workflow-level, then step-level) — later wins. This is how
one step can force an API backend while the rest of the campaign scrapes:

```yaml
steps:
  - name: portals
    query: 'site:{target} inurl:login'
    worker_overrides:
      backend: serper     # requires engines.serper.api_key (see Engines)
```

### Substitution

| Token | Value |
| :--- | :--- |
| `{target}` | The resolved target (`--target` > workflow `target`). |
| `{step}` | Current step name. |
| `{date}` | Run date, `YYYYMMDD`. |
| `{run_id}` | Short id of this run (stable across `--resume`). |

Available in queries, `retry_with`, output paths and description-adjacent
strings. Unknown tokens fail validation with a typo-friendly error; literal
braces such as `ext:{pdf,docx}` are never treated as tokens.

---

## Semantics

### Sequential steps, concurrent queries

Steps always run in order: step *N+1* starts only after *N* finished.
Inside a step, `workers: N` runs that step's queries (`queries:` lists or
`retry_with` batches) on *N* threads — the same thread pool machinery as
`--concurrency`, so caching, dedup and the circuit breaker all apply.

### Threshold retries (`when_results_below` + `retry_with`)

After the step's primary queries finish, unique results (deduplicated by
URL) are counted. Below the threshold → each `retry_with` query runs in
order, and all results merge into the step's output. The step is then
marked:

| Status | Meaning |
| :--- | :--- |
| `done` | Threshold met (or no threshold configured). |
| `below_threshold` | Finished, but still fewer unique results than requested. Recorded; the run continues. |
| `failed` | All queries of the step failed (backend errors exhausted) — `on_error` decides whether the run stops. |

A `below_threshold` step is *not* an error: campaigns against small targets
legitimately return little.

### Failure policy (`on_error`)

- `stop` (default): the first `failed` step aborts the remaining steps —
  fast, deterministic, and re-runnable with `--resume`.
- `continue`: later steps still run; the summary lists the failure.

Step-level errors (including output paths rejected by the environment write
guard) are recorded the same way — a workflow never crashes mid-run with a
half-written state.

### State and `--resume`

Every run persists a JSON state file:

```text
<environment root>/state/workflows/<name>.json    # env active
~/.atdork/state/workflows/<name>.json             # no env
```

It records the `run_id`, per-step status, result counts and written outputs.
`--resume` (or `--workflow-resume`) skips steps whose status is `done` or
`below_threshold` and re-runs only failed/missing steps under the same
`run_id`. Without `--resume` a run starts fresh and overwrites the state.

`--dry-run` never writes state and never calls a search backend — use it to
preview the exact queries a campaign would execute.

### Outputs and the environment guard

Each step may write its merged results:

```yaml
outputs:
  - file: recon/files.json    # relative → inside the environment root/results
    format: json
```

- Formats: `txt`, `json`, `csv` (default: inferred from the extension).
- Relative paths resolve against `<env>/results/` when an
  [environment](environment.md) is active, else the working directory.
- With an active environment **every output goes through the strict write
  guard**: paths escaping the root fail the step — results cannot leak
  outside the workspace.

### Backends, API providers and credit caution

Workflows use the normal search machinery: `backend` accepts scraping
backends, API engines (`serper`, `serpapi`, `brave`) and `profiles:` names;
`fallback_chain`/`search.fallback` and the `--resilient` circuit breaker
apply per query. Each step query counts against your API quota — run
`--dry-run` first, keep `max_results` sane, and prefer scraping backends for
exploratory steps with API backends reserved for `worker_overrides` on the
steps that need them.

---

## Complete example

```yaml
version: 2
workflows:
  recon-acme:
    description: "Full recon sweep for one target"
    target: "example.com"
    workers: 2
    max_results: 50
    region: "us-en"
    steps:
      - name: exposed-files
        query: 'site:{target} ext:(pdf|docx) (intitle:index OR intitle:download)'
        when_results_below: 10
        retry_with:
          - 'site:{target} ext:pdf'
          - 'site:{target} (filetype:doc OR filetype:xls)'
        outputs:
          - file: recon/files.json
            format: json

      - name: login-portals
        queries:
          - 'site:{target} inurl:(login OR signin OR admin)'
          - 'site:{target} intitle:"index of" (.env OR .git)'
        worker_overrides:
          backend: serper
        on_error: continue

      - name: fingerprints
        query: 'site:{target} ("wordpress" OR "drupal") inurl:wp-admin'
        outputs:
          - file: recon/fingerprints.csv
            format: csv
```

```bash
atdork workflow validate recon-acme
atdork workflow run recon-acme --dry-run
atdork workflow run recon-acme                 # fresh run
atdork workflow run recon-acme --resume        # after a stop/failure
```

---

## Tips

- **Validate in CI**: `atdork workflow validate` exits non-zero on bad
  definitions — catch typos before they burn API credits.
- **Environments**: pair workflows with `atdork env create` so every result
  file, cache entry and state file stays inside one portable folder.
- **Combine with packages**: `queries:` can reference installed dork files
  via `--database-dork`-style content only in plain text — copy the dorks
  into `queries:` or generate a workflow with a small script.
- **Debug a step in isolation**: `--step <name>` runs a single step under the
  workflow's own configuration.
