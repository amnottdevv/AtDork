# Basic Usage



 Introduction



This guide covers the most common AtDork commands you'll use daily. Whether you're a security researcher, bug bounty hunter, or OSINT practitioner, these examples will help you get started quickly.



All examples assume you have AtDork installed. If not, see [Installation](installation.md).



---



## Your First Search



The simplest command – search for PDF files on government websites:



```bash

atdork -q "site:gov filetype:pdf" -r 10

```



**Explanation:**

- `-q` – Your search query (dork)

- `-r 10` – Return up to 10 results



---



## Common Use Cases



### 1. Find Exposed Documents



```bash

# PDF files on government sites

atdork -q "site:gov filetype:pdf" -r 20



# Excel files on educational sites

atdork -q "site:edu filetype:xls" -r 20



# Config files with passwords

atdork -q 'filetype:env "DB_PASSWORD"' -r 30

```



### 2. Find Admin Panels



```bash

atdork -q 'intitle:"admin panel" inurl:login' -r 30

```



### 3. Find Directory Listings



```bash

atdork -q 'intitle:"index of" "backup"' -r 20

```



### 4. Find Login Pages



```bash

atdork -q 'inurl:admin login' -r 30

```



### 5. Find WordPress Sites



```bash

atdork -q 'inurl:wp-content' -r 40

```



---



## Save Results



### Save to File



```bash

atdork -q "site:gov filetype:pdf" -r 20 -o results.txt

```



### Save as JSON



```bash

atdork -q "site:gov filetype:pdf" -r 20 --format json -o results.json

```



### Save as CSV



```bash

atdork -q "site:gov filetype:pdf" -r 20 --format csv -o results.csv

```



---



## Batch Processing



### Run Multiple Dorks from a File



Create `dorks.txt`:



```

site:edu filetype:xls

inurl:admin login

intitle:"index of" "backup"

filetype:env "DB_PASSWORD"

```



Then run:



```bash

atdork --batch-file dorks.txt -r 30 -o all_results.json

```



### Run Multiple Dorks Inline



Use `;` as separator:



```bash

atdork -q "site:gov filetype:pdf; site:edu filetype:xls" -r 20 -o results.json

```



---



## Filter Vulnerabilities



### WordPress Detection



```bash

atdork -q "inurl:wp-content" -r 40 --filter-vuln wordpress

```



### Show Vulnerability Counts



```bash

atdork -q "inurl:wp-content" -r 40 --filter-vuln wordpress -v

```



---



## Use Templates (Pre-Built Dorks)



### List Available Templates



```bash

atdork --list-templates

```



### Use a Template



```bash

atdork --template sqli --target example.com -r 30

```



### Preview Template Dorks (Safe Check)



```bash

atdork --template sqli --preview

```



### Combine Templates



```bash

atdork --template sqli,wordpress,exposed_config --target example.com -r 25

```



### Select Specific Dorks



```bash

atdork --template sqli --select 1,3,5 -r 20

```



---



## Use Proxies (Anonymous)



### Single Proxy



```bash

atdork -q "target" --proxy "http:user:pass@host:8080" --strict

```



### Multiple Proxies from File



```bash

atdork -q "target" --proxy-file proxies.txt --strict

```



### Tor Integration



```bash

atdork -q "target" --tor --strict

```



---



## Run with Resilience (Recommended)



For large or automated scans, enable resilience to handle rate limits and blocks:



```bash

atdork --batch-file dorks.txt --resilient --adaptive-delay --proxy-file proxies.txt --strict

```



---



## View History and Resume



### View Search History



```bash

atdork --history

```



### Resume Interrupted Batch



```bash

atdork --resume

```



### Export Database



```bash

atdork --export-db all_results.json

```



---



## Common Flag Reference



| Flag | Description | Example |

|------|-------------|---------|

| `-q` | Your search query | `-q "site:gov filetype:pdf"` |

| `-r` | Number of results (1-100) | `-r 20` |

| `-o` | Save to file | `-o results.json` |

| `--format` | Output format: `txt`, `json`, `csv` | `--format json` |

| `--batch-file` | File with one query per line | `--batch-file dorks.txt` |

| `--filter-vuln` | Vulnerability filter | `--filter-vuln wordpress` |

| `--template` | Load dork template | `--template sqli` |

| `--proxy-file` | Proxy list file | `--proxy-file proxies.txt` |

| `--resilient` | Enable rate limit handling | `--resilient` |

| `--verbose`, `-v` | Show results in real-time | `-v` |



---



## Quick Reference Card



| Task | Command |

|------|---------|

| **Basic search** | `atdork -q "dork" -r 20` |

| **Save to JSON** | `atdork -q "dork" -r 20 --format json -o out.json` |

| **Batch file** | `atdork --batch-file dorks.txt -r 30 -o out.json` |

| **Use template** | `atdork --template sqli --target example.com -r 30` |

| **Filter WordPress** | `atdork -q "inurl:wp-content" --filter-vuln wordpress` |

| **With proxy** | `atdork -q "dork" --proxy-file proxies.txt --strict` |

| **Resilient mode** | `atdork --batch-file dorks.txt --resilient --adaptive-delay` |

| **View history** | `atdork --history` |

| **Resume batch** | `atdork --resume` |



---



## Next Steps



- [Quick Start](quickstart.md) – Get started in 5 minutes

- [CLI Reference](cli-reference.md) – Complete flag reference

- [Resilience System](featuresresilience-system.md) – Handle rate limits automatically

- [Proxy & Anonymity](featuresproxy-anonymity.md) – Stay anonymous

- [Vulnerability Filter](featuresfilter-vuln.md) – Find vulnerabilities faster

- [Template System](featurestemplate-system.md) – Use pre-built dorks

- [Batch Processing](featuresbatch-processing.md) – Run large scans

- [Output Formats](featuresoutput-formats.md) – Export results

