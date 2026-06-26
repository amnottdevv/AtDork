# Proxy & Anonymity

## Introduction

AtDork provides robust proxy management and anonymity features to protect your identity during OSINT operations. Whether you're using a single proxy, rotating through a pool, or routing through Tor, AtDork handles it all with strict mode to prevent IP leaks.

When enabled with `--strict`, AtDork will **never** fall back to a direct connection — it will fail cleanly rather than expose your real IP.

---

## What It Does

| Feature | Description |
|---------|-------------|
| **Proxy Rotation** | Rotate through multiple proxies automatically (HTTP, HTTPS, SOCKS4, SOCKS5) |
| **Tor Integration** | Route traffic through the Tor network with a single flag |
| **Strict Mode** | Fail completely if no proxy is available (no direct connection fallback) |
| **IP Leak Detection** | Detect and stop if your real IP is exposed (`--ip-guard`) |
| **Proxy Cooldown** | Temporarily ban failing proxies (configurable cooldown period) |
| **Auto-Removal** | Permanently remove proxies after N consecutive failures |
| **Proxy Statistics** | Track success/failure rates per proxy |

---

## How to Use

### Single Proxy
```bash
atdork -q "confidential filetype:docx" --proxy "http://user:pass@proxy:8080" --strict
```

### Multiple Proxies (Comma-Separated)
```bash
atdork -q "target" --proxy "http://p1:8080,socks5://p2:1080" --strict
```

### Proxy File (Recommended for large scans)
```bash
atdork -q "target" --proxy-file proxies.txt --strict
```

**Proxy file format (`proxies.txt`):**
```
# HTTP proxies
http://user:pass@dc1.provider.com:3128
http://user:pass@dc2.provider.com:3128

# SOCKS proxies
socks5://res1.provider.com:1080
socks5h://res2.provider.com:1080

# Comments with # are ignored
```

### Tor Integration
```bash
atdork -q "target" --tor --strict
```

### With IP Guard (Leak Detection)
```bash
atdork -q "target" --proxy-file proxies.txt --strict --ip-guard
```

### With Custom Proxy Settings
```bash
atdork -q "target" --proxy-file proxies.txt --strict \
  --proxy-cooldown 120 --max-failures 3
```

---

## How It Works

### 1. Proxy Manager (`proxy_manager.py`)

The Proxy Manager handles the entire proxy lifecycle:

**Proxy Validation**
- Validates proxy format: `scheme://[user:pass@]host:port`
- Automatically skips invalid proxies with a warning

**Proxy Rotation**
- Rotates through proxies in a round-robin fashion
- Skips proxies that are in cooldown (temporarily banned)
- Returns `None` if all proxies are down and `--strict` is not set

**Proxy Cooldown**
- When a proxy fails, it enters cooldown for the specified duration (default: 60s)
- After cooldown, the proxy is tried again

**Proxy Auto-Removal**
- Tracks consecutive failures per proxy
- If a proxy fails `--max-failures` times consecutively, it's removed permanently (default: 3)

### 2. Proxy Selection Flow

```
1. User requests a proxy
   ↓
2. Proxy Manager checks the pool
   ↓
3. If proxy exists → return it
   ↓
4. If proxy fails → report_failure()
   ├─ Increment failure count
   ├─ Enter cooldown (--proxy-cooldown)
   └─ If max_failures reached → remove permanently
   ↓
5. Next request → get_proxy() skips cooldown proxies
   ↓
6. If all proxies are in cooldown and --strict=True → raise RuntimeError
   If --strict=False → return None (fallback to direct connection)
```

### 3. IP Guard (`ip_guard.py`)

When `--ip-guard` is enabled, AtDork actively monitors for IP leaks:

**How It Works:**
1. **Establish Baseline**: When the scan starts, IP Guard makes a test request through the proxy to determine the visible IP address
2. **Periodic Checks**: Every few queries, IP Guard rechecks the visible IP
3. **Leak Detection**: If the visible IP changes to your real IP (detected via `httpbin.org/ip`), AtDork stops immediately
4. **Header Inspection**: Checks response headers like `X-Forwarded-For`, `CF-Connecting-IP`, and `X-Real-IP` for your real IP

**Panic Message Example:**
```
════════════════════════════════════════════════════════════
  ❌  IP LEAK DETECTED – PROGRAM STOPPED
════════════════════════════════════════════════════════════

  Your real IP address has been exposed to the public.

  ┌─────────────────────────────────────────────────────────┐
  │  Your IP (real):    203.0.113.45                      │
  │  Expected IP:       192.168.1.100                     │
  └─────────────────────────────────────────────────────────┘

  What happened:
  AtDork detected that your real IP address was visible to
  external servers while using proxy/Tor. This could happen if:
  - All proxies failed and a direct connection was made
  - The proxy is not anonymous (transparent proxy)
  - DNS leak occurred

  ⚠️  AtDork has stopped to prevent further exposure.
════════════════════════════════════════════════════════════
```

### 4. Tor Integration

AtDork integrates with Tor by connecting to the local SOCKS5 proxy:

- **Default endpoint**: `socks5h://127.0.0.1:9050`
- **DNS Resolution**: Uses `socks5h` to prevent DNS leaks (DNS resolves through Tor)
- **Prerequisite**: Tor service must be running locally

**Starting Tor:**
- Linux: `sudo systemctl start tor`
- macOS: `brew services start tor`
- Windows: Launch Tor Browser (runs SOCKS5 on port 9050)

---

## Full Flag Reference

| Flag | Description | Default |
|------|-------------|---------|
| `--proxy` | Comma-separated proxy URLs | None |
| `--proxy-file` | File path with proxy URLs (one per line) | None |
| `--tor` | Use Tor SOCKS5 proxy (`socks5h://127.0.0.1:9050`) | Disabled |
| `--strict` | Fail if all proxies are down (no direct fallback) | Disabled |
| `--proxy-cooldown` | Cooldown after proxy failure (seconds) | 60 |
| `--max-failures` | Remove proxy after N consecutive failures | 3 |
| `--ip-guard` | Enable IP leak detection (requires --strict) | Disabled |

---

## Real-World Use Cases

### 1. Bug Bounty Recon with Proxy Rotation
```bash
atdork --template sqli,xss,lfi --target target.com \
  --proxy-file premium_proxies.txt --strict --resilient \
  --format json -o recon.json
```

### 2. Anonymous Dark Web Monitoring
```bash
atdork -q "site:pastebin.com password" -r 20 \
  --tor --strict --resilient --ip-guard \
  --delay 5 --no-dedup
```

### 3. Unattended Nightly Scan with Proxy Fallback
```bash
atdork --batch-file weekly_dorks.txt \
  --proxy-file rotating_proxies.txt --strict \
  --proxy-cooldown 120 --max-failures 2 \
  --resilient --format csv --output-dir /reports/
```

### 4. Testing Proxy Quality
```bash
atdork -q "test" -r 1 \
  --proxy-file proxies.txt --strict \
  --verbose --debug
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **Proxy format error** | Use correct format: `scheme://user:pass@host:port` |
| **All proxies in cooldown** | Increase `--proxy-cooldown`, add more proxies, or disable `--strict` |
| **Tor not working** | Ensure Tor service is running: `systemctl start tor` (Linux) or launch Tor Browser |
| **IP leak detected** | Check proxies (some are transparent), use SOCKS5h for DNS leaks, enable `--ip-guard` |
| **Proxy removed permanently** | Increase `--max-failures` or use more reliable proxies |