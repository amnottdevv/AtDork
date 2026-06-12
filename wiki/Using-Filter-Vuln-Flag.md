# Using the `--filter-vuln` Flag

## Quick Reference

The `--filter-vuln` flag intelligently filters AtDork results to show **only actual vulnerable web applications**, eliminating false positives, honeypots, and non-applicable results.

---

## Basic Syntax

```bash
python main.py -q "your-dork-query" --filter-vuln [PLATFORM]
```

**Supported Platforms:**
- `wordpress` – Detect vulnerable WordPress instances
- `joomla` – Detect vulnerable Joomla instances *(planned)*
- `drupal` – Detect vulnerable Drupal instances *(planned)*

---

## How It Works

### Without Filter (Raw Results)

```bash
python main.py -q "inurl:wp-admin" -r 50
```

**Results include:**
- ✅ Real WordPress installations
- ❌ Honeypots (fake targets)
- ❌ Parked domains
- ❌ Redirects & CDNs
- ❌ Non-WordPress pages with "wp-admin" keyword

**Problem:** 30-40% false positives that waste your time

---

### With Filter (Cleaned Results)

```bash
python main.py -q "inurl:wp-admin" -r 50 --filter-vuln wordpress
```

**Results include:**
- ✅ Verified WordPress installations
- ✅ Active admin panels
- ✅ Potentially vulnerable endpoints
- ❌ Honeypots (automatically removed)
- ❌ Decoys (automatically removed)
- ❌ Non-WordPress pages (automatically removed)

**Result:** 80%+ accuracy with actionable targets

---

## WordPress Vulnerability Filtering

### What Gets Detected

The WordPress vulnerability filter identifies:

#### 1. **Active WordPress Installations**
- Detects WordPress core files (wp-content, wp-includes)
- Verifies active database connections
- Confirms responsive admin panels

#### 2. **Login Page Availability**
- Confirms wp-login.php is accessible
- Validates authentication forms
- Checks for redirects/protections

#### 3. **Common Vulnerabilities**
- Outdated WordPress versions (in HTTP headers)
- Vulnerable plugin directory listings
- Exposed configuration files
- XML-RPC availability (brute-force vector)

#### 4. **False Positive Removal**
- Removes honeypots (intentional traps)
- Removes parked domains
- Removes CDN/proxy responses
- Removes non-WordPress pages with matching keywords

---

## Real-World Examples

### Example 1: Find Vulnerable WordPress Admin Panels

```bash
python main.py -q "inurl:wp-admin" -r 100 --filter-vuln wordpress
```

**Expected output:** Real WordPress login pages only

---

### Example 2: Find Outdated WordPress Versions

```bash
python main.py -q "WordPress 5.0" -r 50 --filter-vuln wordpress
```

**Expected output:** WordPress 5.0 installations (released 2018, has known CVEs)

---

### Example 3: Find XML-RPC Endpoints (Brute-Force Vectors)

```bash
python main.py -q "inurl:xmlrpc.php" -r 50 --filter-vuln wordpress --strict-filter
```

**Expected output:** Active XML-RPC endpoints on WordPress sites

---

### Example 4: Batch Assessment with Multiple Dorks

```bash
# Create dorks file
cat > wordpress_dorks.txt << EOF
inurl:wp-admin
inurl:xmlrpc.php
"WordPress Version"
site:example.com inurl:wp-content
EOF

# Run with vulnerability filtering
python main.py --batch-file wordpress_dorks.txt \
  --filter-vuln wordpress \
  --concurrency 3 \
  --format json \
  --output-dir assessment_results \
  --strict-filter
```

---

## Combining With Other Flags

### With `--strict-filter`

For highest quality results:

```bash
python main.py -q "inurl:wp-admin" -r 50 \
  --filter-vuln wordpress \
  --strict-filter
```

**This combination:**
- ✅ Removes honeypots
- ✅ Requires valid snippets
- ✅ Enforces minimum title length
- ✅ Validates URL format

---

### With Output Formats

#### JSON Output (Recommended)

```bash
python main.py -q "inurl:wp-admin" -r 50 \
  --filter-vuln wordpress \
  --format json \
  -o wordpress_vulns.json
```

**Example JSON output:**
```json
[
  {
    "title": "My Website › WordPress Admin",
    "href": "https://example.com/wp-admin/",
    "body": "Login",
    "vulnerability_score": 0.87,
    "vuln_type": "wordpress_admin_exposed",
    "detected_version": "5.0.1",
    "confidence": "high"
  }
]
```

---

#### CSV Output (For Reports)

```bash
python main.py -q "inurl:wp-admin" -r 50 \
  --filter-vuln wordpress \
  --format csv \
  -o wordpress_report.csv
```

---

### With Proxy/Tor

For anonymous scanning:

```bash
python main.py -q "inurl:wp-admin" -r 50 \
  --filter-vuln wordpress \
  --tor \
  --strict \
  --delay 3
```

---

### With Rate Limiting

To avoid detection:

```bash
python main.py -q "inurl:wp-admin" -r 50 \
  --filter-vuln wordpress \
  --delay 5 \
  --retries 2 \
  --timeout 15
```

---

## Interpreting Results

### Vulnerability Score

Each result includes a vulnerability score (0.0 - 1.0):

- **0.9+** – Critical: Immediate action required
  - Active, accessible admin panel
  - Potentially exploitable
  
- **0.7-0.8** – High: Investigate further
  - WordPress detected
  - Possible vulnerabilities
  
- **0.5-0.6** – Medium: May require additional verification
  - Indirect WordPress detection
  - Needs manual verification

---

### Confidence Levels

- **high** – Strong evidence of vulnerability (>90% confidence)
- **medium** – Moderate evidence (70-90% confidence)
- **low** – Weak evidence, manual verification recommended (<70% confidence)

---

## Workflow for Vulnerability Assessment

### Step 1: Initial Scan

```bash
python main.py -q "inurl:wp-admin" -r 100 \
  --filter-vuln wordpress \
  --format json \
  -o initial_scan.json
```

### Step 2: Filter High-Confidence Results

```bash
# Filter JSON for high confidence results
cat initial_scan.json | grep -i '"confidence": "high"'
```

### Step 3: Manual Verification

Visit top results to confirm:
- Real WordPress installation
- Login page is accessible
- No WAF/IDS protections
- Version information

### Step 4: Document & Report

```bash
# Create final report
python main.py -q "inurl:wp-admin" -r 50 \
  --filter-vuln wordpress \
  --strict-filter \
  --format json \
  -o final_assessment_$(date +%Y%m%d_%H%M%S).json
```

---

## Performance Tips

### 1. Use Backend Filtering

DuckDuckGo is faster but less comprehensive:

```bash
# Fast but less data
python main.py -q "inurl:wp-admin" -r 50 \
  --backend duckduckgo \
  --filter-vuln wordpress
```

Google is slower but more comprehensive:

```bash
# Slower but more results
python main.py -q "inurl:wp-admin" -r 100 \
  --backend google \
  --filter-vuln wordpress
```

---

### 2. Use Batch Processing for Multiple Queries

```bash
python main.py --batch-file queries.txt \
  --filter-vuln wordpress \
  --concurrency 5 \
  --format json \
  --output-dir results
```

---

### 3. Reduce Results Count for Speed

```bash
# Faster scan
python main.py -q "inurl:wp-admin" -r 20 --filter-vuln wordpress

# Comprehensive scan (slower)
python main.py -q "inurl:wp-admin" -r 100 --filter-vuln wordpress
```

---

## Troubleshooting

### Issue: No Results After Filtering

**Possible causes:**
1. Query is too specific (try broader dork)
2. All results were false positives (expected with some queries)
3. Backend service is rate-limiting

**Solution:**
```bash
# Try different backend
python main.py -q "inurl:wp-admin" -r 50 \
  --backend google \
  --filter-vuln wordpress \
  --delay 2
```

---

### Issue: Still Seeing Honeypots

**Possible causes:**
1. Honeypots fool both automated and manual detection
2. Need additional manual verification

**Solution:**
```bash
# Use manual verification
python main.py -q "inurl:wp-admin" -r 50 \
  --filter-vuln wordpress \
  --strict-filter \
  --format json -o results.json

# Then manually review each result
cat results.json | jq '.[] | .href'
```

---

## Best Practices

### ✅ DO

- ✅ Always use `--filter-vuln wordpress` with WordPress dorks
- ✅ Combine with `--strict-filter` for highest quality
- ✅ Use `--delay` to avoid detection
- ✅ Document your findings
- ✅ Only scan authorized targets

### ❌ DON'T

- ❌ Don't disable vulnerability filtering without good reason
- ❌ Don't scan without authorization
- ❌ Don't exploit vulnerabilities you find
- ❌ Don't disclose findings publicly without responsible disclosure
- ❌ Don't use results for malicious purposes

---

## Legal Considerations

Using `--filter-vuln` to identify vulnerabilities is **legal ONLY when:**

1. ✅ You have **written authorization** from the target
2. ✅ It's part of **authorized security research**
3. ✅ It's within **bug bounty programs**
4. ✅ It's for **authorized penetration testing**

**Unauthorized vulnerability scanning is illegal in most jurisdictions.**

---

## Next Steps

1. Learn more about [WordPress-specific dorks](https://github.com/amnottdevv/AtDork/wiki/WordPress-Dork-Queries)
2. Explore [Advanced Filtering Options](https://github.com/amnottdevv/AtDork/wiki/Advanced-Filtering-Guide)
3. Review [Legal & Ethical Guidelines](https://github.com/amnottdevv/AtDork/wiki/Legal-and-Ethical-Guidelines)

---

**Version:** 1.0  
**Last Updated:** June 2026  
**Maintainer:** amnottdevv
