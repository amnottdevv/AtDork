# Engines & Providers

AtDork searches through two kinds of engines:

1. **Built-in scraping engines** — provided by the `ddgs` library, no account
   needed (default behaviour).
2. **Third-party API providers** — official paid/free search APIs
   (**Serper.dev**, **SerpApi**, **Brave Search API**), configured under
   `engines:` in `atdork.yml`. Deterministic results, higher reliability, but
   they consume your API credits.

Both kinds are selected the same way — with `--backend`, `search.backend`, or
a `profiles:` chain — and both feed the identical downstream pipeline
(validation, filtering, dedupe, cache, resume, output formats).

---

## Built-in engines (scraping)

| Backend | Notes |
|---------|-------|
| `auto` | Default: ddgs picks its best source per query. |
| `google` | Google via ddgs. |
| `bing` | Bing via ddgs. |
| `duckduckgo` | DuckDuckGo (first entry of the default fallback chain). |
| `brave` | Brave **scraping** backend — unless overridden by `engines.brave` (API). |
| `mojeek` | Mojeek — light scraping footprint. |
| `startpage` | Startpage. |
| `wikipedia` | Wikipedia (last default fallback). |
| `yandex`, `yahoo` | Available via ddgs. |

The **default fallback chain** (when `search.fallback` is not configured) is:

```
duckduckgo → bing → brave → mojeek → startpage → wikipedia
```

```bash
atdork -q "inurl:admin"                    # auto
atdork -q "inurl:admin" --backend google   # force one scraping backend
atdork -q "test" --no-fallback-backends    # single backend only, no chain
```

No API key, no account, no config required.

---

## API providers

Add them under `engines:` in `atdork.yml` (see
[Configuration](configuration.md#engines)):

```yaml
version: 2
engines:
  serper:
    type: api
    api_key: ${SERPER_API_KEY}
    qps: 1
  serpapi:
    type: api
    api_key: ${SERPAPI_KEY}
    qps: 1
  brave:
    type: api
    api_key: ${BRAVE_API_KEY}
    qps: 1
```

```bash
export SERPER_API_KEY=...     # or SERPAPI_KEY / BRAVE_API_KEY
atdork -q "site:github.com password" --backend serper
```

### Supported providers at a glance

| Engine | Endpoint | Key env var | Free tier* | Per-request cap | `qps` default |
|--------|----------|-------------|------------|-----------------|---------------|
| `serper` | `POST google.serper.dev/search` | `SERPER_API_KEY` | one-time credits (≈2,500) | 100 | 1.0 |
| `serpapi` | `GET serpapi.com/search` | `SERPAPI_KEY` | 100 searches/month | 100 | 1.0 |
| `brave` | `GET api.search.brave.com/res/v1/web/search` | `BRAVE_API_KEY` | 2,000 queries/month | **20** | 1.0 |

\* Free-tier figures are what the providers published last we checked —
always confirm on their pricing pages. `qps` is AtDork's **local** limiter
(minimum interval between your own requests); raise or lower it to match
your plan (`qps: 0` disables it).

### Parameter support matrix

How AtDork's common search parameters map per provider:

| Parameter | serper | serpapi | brave |
|-----------|--------|---------|-------|
| query + `max_results` | ✅ `q`, `num` | ✅ `q`, `num` | ✅ `q`, `count` (max 20) |
| `region` (`us-en`) | ✅ `gl`/`hl` | ✅ `gl`/`hl` | ✅ `country`/`search_lang` |
| `safesearch` | ⚪ ignored | ⚪ ignored (engine-dependent) | ✅ `safesearch` off/moderate/strict |
| `timelimit` (d/w/m/y) | ⚪ ignored | ✅ `tbs=qdr:d…` | ✅ `freshness=pd/pw/pm/py` |
| proxy + custom UA | ✅ applied per request | ✅ | ✅ |

Provider-specific options can be passed through `engines.<name>` and land in
the request (e.g. `engine: google-news` for serpapi, `location: Paris, France`
for serper, `offset: 20` for brave):

```yaml
engines:
  serpapi:
    type: api
    api_key: ${SERPAPI_KEY}
    engine: google
    tbs: ""            # extra query params via options
```

### Result normalisation

Every provider response is normalised to AtDork's internal shape —
`{title, href, body}` — so filters, dedupe, cache, resume and all output
formats behave identically to scraping results.

---

## Backend resolution & override rules

For every backend name AtDork tries, resolution order is:

1. **Registry** — is the name configured under `engines:`?
   → use the API provider. A configured name **overrides** a built-in backend
   with the same name (`engines.brave` → Brave Search API instead of
   ddgs scraping).
2. Otherwise → built-in `ddgs` scraping path.

```bash
# API directly
atdork -q "inurl:test" --backend serper

# explicit chain: scraping first, API last
atdork -q "inurl:test" --backend google,serper

# profile from atdork.yml
atdork -q "inurl:test" --backend resilient
```

### The fallback chain

```yaml
search:
  backend: auto
  fallback: [google, serper, brave]   # or "google,serper,brave"
```

Behaviour:

| Situation | Queue |
|-----------|-------|
| `backend: auto` + chain configured | `auto` first, then the chain |
| single backend + chain | that backend, then the chain |
| comma list (`google,serper`) | used as-is |
| profile name | profile list as-is (even with `--no-fallback-backends`) |
| no chain configured | built-in ddgs default chain |

What happens on **provider errors**:

| Error kind | Detected from | Behaviour |
|------------|---------------|-----------|
| `quota` (credits exhausted) | HTTP 402/403, body keywords, serpapi `error` field | provider skipped, **next backend immediately**, no retry |
| `rate_limit` (429) | HTTP 429 | same as quota (treated as rate limit) |
| `auth` (bad key) | HTTP 401/403 | skipped, clear log line |
| `config` (key not set) | empty `api_key` | skipped; raised at the end if nothing was found |
| `network` / `parse` / `api` | timeouts, bad JSON, other 4xx/5xx | retried on the same backend with backoff, then next |

> **Credit caution:** a provider in the chain is queried for *every* query
> that reaches it — including queries that legitimately have **zero results**
> (an empty scraper result advances to the next backend). If API credits are
> precious, either keep API engines **out** of `fallback` and invoke them
> explicitly with `--backend serper`, or make them the **first** entry so
> you pay only one API call per query instead of chain-tail calls after every
> empty scrape.

---

## Configuration reference for `engines.<name>`

| Key | Default | Description |
|-----|---------|-------------|
| `type` | `api` | Only `api` is supported (validated at load). |
| `provider` | *(name)* | Implementation when the key differs from the class name (e.g. two serper accounts: `myserper: {provider: serper, ...}`). |
| `api_key` | — | `${ENV}` interpolation strongly recommended; unset `${ENV}` fails at load, empty value fails at query time with a clear error. |
| `qps` | `1.0` | Local rate limit (requests/second, `0` = unlimited). Shared across worker threads. |
| `timeout` | `10` | HTTP timeout in seconds. |
| *(extra)* | — | Passed to the provider as a request option (`engine`, `gl`, `hl`, `location`, `country`, `search_lang`, `offset`, ...). |

---

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `Config error: ... engines.serper.api_key: environment 'SERPER_API_KEY' is not set` | Export the variable, use `${SERPER_API_KEY:-}`, or remove the engine. |
| `engines.serper.api_key is not set — export SERPER_API_KEY...` at query time | Engine configured with an empty/literal-empty key; set the key. |
| `API quota exceeded (rate limit): ...` in logs | Out of credits — AtDork moves to the next backend automatically. Check your provider dashboard. |
| `Rate limited: ...` | Provider throttling — lower `qps`, or let the chain continue. |
| `Authentication failed: ...` | Key invalid/rotated — regenerate and update the env var. |
| `unknown provider 'x' (supported: brave, serpapi, serper)` | `provider:` / engine name typo in `engines:`. |
| Brave results stop at 20 | Free-tier per-request cap (`count ≤ 20`); paginate via `offset` option or use another provider for larger `max_results`. |

**Keys never appear in logs**: requests/responses are passed through the
redactor (`api_key=***`, `***last4`, masked URL credentials), so it is safe to
run with `--debug` when diagnosing provider issues.
