# Quick Start Guide

Get up and running with AtDork in less than a minute. These fundamental workflows illustrate how to structure passive target reconnaissance.

---

## 1. Execute a Standard Search Query

Discover exposed PDF archives hosted on public government domains. By default, AtDork targets `20` maximum entries using the optimal available engine backend.

````bash
atdork -q "site:gov filetype:pdf" -r 10
````

## 2. Storing Extracted Data to Disk

Save search index outputs straight to a cleanly parsed JSON payload file for upstream analysis:

````bash
atdork -q "intitle:index.of mp3" -r 20 --format json -o music.json
````

## 3. High-Throughput Batch Processing

Execute dozens of complex dorking patterns simultaneously.

1. Create a plain text payload containing one dork profile per line, named `dorks.txt`:
    ````text
    site:edu filetype:xls
    inurl:admin login
    intitle:"index of" "backup"
    ````

2. Pass the text map straight into the engine batch engine:
    ````bash
    atdork --batch-file dorks.txt -r 30 --format csv -o results.csv
    ````

## 4. Masking Network Identities

Route traffic natively through a dedicated proxy gate using full enforcement restrictions:

````bash
atdork -q "confidential filetype:docx" --proxy "[http://user:pass@proxy.example.com:8080](http://user:pass@proxy.example.com:8080)" --strict
````