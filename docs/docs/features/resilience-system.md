# Resilience System

## Introduction

The Resilience System is AtDork's intelligent fault‑tolerance engine. It ensures that large‑scale OSINT operations continue smoothly even when search engines block you, proxies fail, or network connections drop.

Activated with `--resilient`, it coordinates seven specialised modules under `core/case/` to handle every failure scenario automatically.

---

## What It Does

| Scenario | Without Resilience | With Resilience |
|----------|-------------------|-----------------|
| Google returns HTTP 429 (Rate Limit) | All subsequent queries fail | Switches to Startpage, cools down Google for 120s |
| Proxy dies mid‑batch | Batch crashes | Rotates to next healthy proxy |
| All backends blocked | Scan fails completely | Falls back through 5+ search engines until one works |
| Temporary network timeout | Query fails permanently | Retries up to 3x with exponential backoff |
| Backend returns empty results | Wastes retries on dead backend | Immediately switches to next backend |

---

## How to Use

### Basic Command
```bash
atdork --batch-file dorks.txt --resilient
```

### With Adaptive Delay (Recommended for large scans)
```bash
atdork --batch-file dorks.txt --resilient --adaptive-delay --concurrency 5 --delay 2
```

### For Bug Bounty Reconnaissance
```bash
atdork --template sqli,xss,lfi --target target.com \
  --proxy-file proxies.txt --strict --resilient \
  --concurrency 3 --format json -o recon.json
```

### For Stealth Monitoring (with IP Guard)
```bash
atdork -q "site:gov.in filetype:pdf confidential" -r 30 \
  --tor --strict --resilient --ip-guard --delay 3 -v
```

### Automated Weekly Reports (Unattended)
```bash
atdork --batch-file weekly_dorks.txt \
  --proxy-file premium_proxies.txt --strict --resilient \
  --concurrency 5 --format csv --output-dir /reports/2026-W25/
```

---

## How It Works

### 1. Error Classifier (`error_classifier.py`)

Classifies every exception into one of five categories:

| Category | Description | Action |
|----------|-------------|--------|
| **TRANSIENT** | Timeout, connection reset | Retry with backoff |
| **RATE_LIMIT** | HTTP 429, "too many requests" | Switch backend, cooldown |
| **BLOCKED** | HTTP 403, CAPTCHA, "access denied" | Switch backend + rotate proxy |
| **PROXY_FAIL** | Proxy dead, connection refused | Rotate to next proxy |
| **FATAL** | Parsing error, bug | Abort immediately |

---

### 2. Circuit Breaker (`circuit_breaker.py`)

Prevents hammering dead backends/proxies. After a resource fails 3 times consecutively, the circuit opens.

```
Backend fails 3 times → Circuit OPEN for 120s
After 120s → HALF-OPEN: one request allowed
If succeeds → CLOSED (healthy again)
If fails → OPEN for another 120s
```

---

### 3. Fallback Manager (`fallback_manager.py`)

Decides the best action based on the error category and current state:

| Error Category | Decision |
|----------------|----------|
| **RATE_LIMIT** | Switch to next healthy backend |
| **BLOCKED** | Switch backend + rotate proxy |
| **PROXY_FAIL** | Rotate proxy; if all proxies dead, cooldown |
| **TRANSIENT** | Retry same resource |
| **FATAL** | Abort with clear error |

---

### 4. Retry Handler (`retry_handler.py`)

Implements exponential backoff with jitter to avoid overwhelming servers:

| Attempt | Delay (approx) |
|---------|----------------|
| 1st | 2s |
| 2nd | 4s |
| 3rd | 8s |

> **Jitter** (random variance) prevents all threads from retrying at the exact same moment.

---

### 5. Adaptive Delay (`adaptive_delay.py`)

Adjusts delay per backend based on real‑time response codes:

- **Success (200 + results):** Delay decreases by 10% (down to 0.1s minimum)
- **Rate limit (429):** Delay doubles (up to 60s maximum)
- **Other errors:** Delay unchanged

At the end of a batch, recommendations are displayed:

```
Rate Limiter Recommendations:
  google: 8/20 rate-limited. Increase delay to 5.0s or switch backend.
  startpage: 0/15 rate-limited. Everything healthy at 0.3s.
```

---

### 6. IP Guard (`ip_guard.py`)

When `--strict` is active, IP Guard periodically checks that your real IP is not being exposed:

1. Establishes a baseline (IP visible through proxy/Tor)
2. Checks every few queries that the visible IP hasn't changed to your real IP
3. Inspects response headers (`X-Forwarded-For`, `CF-Connecting-IP`) for leaks
4. If a leak is detected, AtDork halts immediately with a detailed panic message

```
════════════════════════════════════════════════════════════
  ❌  IP LEAK DETECTED – PROGRAM STOPPED
════════════════════════════════════════════════════════════

  Your real IP address has been exposed to the public.

  ┌─────────────────────────────────────────────────────────┐
  │  Your IP (real):    203.0.113.45                      │
  │  Expected IP:       192.168.1.100                     │
  └─────────────────────────────────────────────────────────┘
```

---

### 7. Stats Collector (`stats.py`)

Collects and displays runtime statistics:

```
════════════════════════════════════════════════════════════
  AtDork Runtime Statistics
════════════════════════════════════════════════════════════
  Total runtime: 142.3s

🔄 BACKENDS
   google       | Req: 45 | OK: 32 | 429: 13 | 403: 0
   startpage    | Req: 12 | OK: 12 | 429: 0  | 403: 0

🛡️ PROXIES
   Active: 5 | Banned: 2 | Removed: 1
   Success: 44 | Failure: 8

🔁 FALLBACKS
   Triggered: 5 | Successful: 4 | Failed: 1

🔄 RETRIES
   Attempted: 8 | Successful: 6 | Failed: 2

⚡ CIRCUIT BREAKER
   Total opened: 2

🛡️ IP GUARD
   Checks: 12 | Leaks: 0
════════════════════════════════════════════════════════════
```

---

## Full Flag Reference

| Flag | Description | Default |
|------|-------------|---------|
| `--resilient` | Enable circuit breaker & backend fallback | Disabled |
| `--adaptive-delay` | Enable adaptive rate limiting | Disabled |
| `--ip-guard` | Enable IP leak detection (requires --strict) | Disabled |
| `--retries` | Retry attempts on failure | 2 |
| `--delay` | Base delay between requests (seconds) | 0 |
| `--proxy-cooldown` | Cooldown after proxy failure (seconds) | 60 |
| `--max-failures` | Remove proxy after N failures | 3 |

---

## Real-World Use Cases

### 1. Unattended Nightly Recon
```bash
atdork --batch-file weekly_dorks.txt \
  --proxy-file proxies.txt --strict --resilient --adaptive-delay \
  --concurrency 5 --format json --output-dir /reports/$(date +\%Y-\%W)/
```

### 2. WordPress Vulnerability Scanning with Auto-Recovery
```bash
atdork -q "inurl:wp-content" -r 40 \
  --filter-vuln wordpress --resilient \
  --exec-on-vuln "wpscan --url {} --enumerate p" \
  --exec-parallel 2 --exec-timeout 60
```

### 3. Continuous Dark Web / Sensitive Data Search
```bash
atdork -q "site:pastebin.com password" -r 20 \
  --tor --strict --resilient --ip-guard \
  --delay 5 --no-dedup \
  --exec "echo {} >> pastebin_urls.txt"
```