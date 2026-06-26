# Persistent Configuration

Instead of constantly typing long CLI flag configurations into the terminal session, store your global parameters in a structured configuration layout file named `atdork.yaml`.

---

## Default Configuration Profile

Create an `atdork.yaml` file in your active workspace directory. AtDork automatically discovers and maps these options during launch sequence phases:

````yaml
# AtDork Configuration File Map
max_results: 30
region: "uk-en"
safesearch: "off"
delay: 1.5
format: "json"
output_dir: "./results"
proxy_file: "proxies.txt"
concurrency: 3
resilient: true
adaptive_delay: true
ip_guard: true
cache: true
cache_ttl: 12
````

---

## Precedence Hierarchies

AtDork resolves structural configurations according to an explicit, fixed priority scheme:

````text
 [ 1. Command Line Flag Options ]  (Highest Precedence - Overrides All)
                │
                ▼
 [ 2. Local File: atdork.yaml  ]  (Overrides Built-In Packaging Defaults)
                │
                ▼
 [ 3. Internal Program Engine  ]  (Fallback Core Hardcoded baselines)
````