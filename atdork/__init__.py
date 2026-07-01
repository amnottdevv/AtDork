"""
AtDork - Professional OSINT Library

Usage:
    from atdork import search, batch_search, validate_results, filter_vulnerable
    from atdork import load_templates, list_templates

    # Single search
    results = search("site:gov filetype:pdf", max_results=20)

    # Batch search
    results = batch_search(["dork1", "dork2"], max_results=10)

    # Validate results
    clean = validate_results(results, min_title=10, check_spam=True)

    # Filter vulnerabilities
    vuln, safe, _ = filter_vulnerable(results, filter_arg="wordpress")

    # Load templates
    dorks = load_templates("sqli", target="example.com")
"""

from atdork.core.scanner import search_dork as search
from atdork.core.batch_runner import run_batch as batch_search
from atdork.lib.validator import filter_results as validate_results
from atdork.core.filter_vuln import filter_vulnerable
from atdork.core.template_dork import load_template_dorks as load_templates
from atdork.core.template_dork import list_available_templates as list_templates
from atdork.core.proxy_manager import create_proxy_manager
from atdork.core.database import Database
from atdork.core.manage_cache import SearchCache
from atdork.core.post_processor import PostProcessor, extract_urls, extract_vulnerable_urls

# Case modules
from atdork.core.case.circuit_breaker import CircuitBreaker
from atdork.core.case.retry_handler import RetryHandler
from atdork.core.case.adaptive_delay import AdaptiveDelay
from atdork.core.case.fallback_manager import FallbackManager

__version__ = "1.3.9"
__author__ = "alzzmarket"
