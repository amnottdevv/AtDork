"""
Atdork – Post Processor (core/post_processor.py)
Menjalankan perintah eksternal untuk setiap hasil pencarian.

Fitur:
- --exec "command {}" → jalankan command untuk setiap URL
- --exec-on-vuln "command {}" → hanya untuk hasil rentan
- --exec-parallel N → jumlah proses paralel
- --exec-timeout N → batas waktu per command
"""

import subprocess
import threading
import logging
import shlex
from typing import List, Dict, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

logger = logging.getLogger(__name__)


class PostProcessor:
    """
    Menjalankan perintah eksternal untuk setiap hasil pencarian.

    Args:
        command: Template perintah (gunakan {} untuk placeholder URL).
        parallel: Jumlah proses paralel (default 1).
        timeout: Batas waktu per perintah dalam detik (default 30).
        on_success: Callback opsional saat perintah sukses.
        on_error: Callback opsional saat perintah gagal.
    """

    def __init__(
        self,
        command: str,
        parallel: int = 1,
        timeout: int = 30,
        on_success: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
    ):
        if not command or "{}" not in command:
            raise ValueError("Command harus mengandung placeholder '{}' untuk URL")

        self.command = command
        self.parallel = max(1, parallel)
        self.timeout = timeout
        self.on_success = on_success
        self.on_error = on_error

        # Statistik
        self.stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "timeout": 0,
        }

    def _run_single(self, url: str) -> Dict:
        """
        Jalankan perintah untuk satu URL.
        Returns dict dengan: url, success, stdout, stderr, returncode, error
        
        FIX HIGH: Improved security with input validation and safe command construction
        """
        result = {
            "url": url,
            "success": False,
            "stdout": "",
            "stderr": "",
            "returncode": -1,
            "error": None,
        }

        try:
            # FIX HIGH: Validate URL to prevent injection
            if not isinstance(url, str) or not url.strip():
                result["error"] = "Invalid URL (empty or not string)"
                self.stats["failed"] += 1
                return result
            
            # FIX HIGH: Check for suspicious patterns that could bypass shlex.quote
            suspicious_chars = ['$', '`', '\n', '\r', '\0']
            if any(char in url for char in suspicious_chars):
                logger.warning(f"URL contains suspicious characters, skipping: {url[:50]}")
                result["error"] = "URL contains suspicious characters"
                self.stats["failed"] += 1
                return result

            # Bangun perintah dengan proper escaping
            url_escaped = shlex.quote(url)
            cmd = self.command.replace("{}", url_escaped)
            
            # FIX HIGH: Log command without exposing sensitive data
            logger.debug(f"Executing command with URL placeholder (URL length: {len(url)} chars)")

            # Jalankan dengan strict safety settings
            process = subprocess.run(
                cmd,
                shell=True,  # Required for command templates, but URL is properly escaped
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            result["returncode"] = process.returncode
            result["stdout"] = process.stdout.strip()
            result["stderr"] = process.stderr.strip()

            if process.returncode == 0:
                result["success"] = True
                self.stats["success"] += 1
                if self.on_success:
                    try:
                        self.on_success(url, result)
                    except Exception as e:
                        logger.error("Error di on_success callback: %s", e)
            else:
                self.stats["failed"] += 1
                result["error"] = f"Exit code: {process.returncode}"
                if self.on_error:
                    try:
                        self.on_error(url, result)
                    except Exception as e:
                        logger.error("Error di on_error callback: %s", e)

        except subprocess.TimeoutExpired:
            self.stats["timeout"] += 1
            result["error"] = f"Timeout setelah {self.timeout}s"
            if self.on_error:
                try:
                    self.on_error(url, result)
                except Exception as e:
                    logger.error("Error di on_error callback: %s", e)

        except Exception as e:
            self.stats["failed"] += 1
            result["error"] = str(e)
            logger.error("Error menjalankan command untuk %s: %s", url[:50], e)
            if self.on_error:
                try:
                    self.on_error(url, result)
                except Exception as e2:
                    logger.error("Error di on_error callback: %s", e2)

        return result

    def process(self, urls: List[str]) -> List[Dict]:
        """
        Jalankan perintah untuk setiap URL dalam daftar.

        Args:
            urls: Daftar URL yang akan diproses.

        Returns:
            List hasil untuk setiap URL.
        """
        if not urls:
            return []

        self.stats = {"total": len(urls), "success": 0, "failed": 0, "timeout": 0}
        results = []

        if self.parallel > 1:
            with ThreadPoolExecutor(max_workers=self.parallel) as executor:
                future_to_url = {
                    executor.submit(self._run_single, url): url for url in urls
                }
                for future in as_completed(future_to_url):
                    url = future_to_url[future]
                    try:
                        result = future.result(timeout=self.timeout + 5)
                        results.append(result)
                    except TimeoutError:
                        logger.error("Timeout menunggu hasil untuk %s", url[:50])
                        results.append({
                            "url": url,
                            "success": False,
                            "error": "Future timeout",
                        })
                        self.stats["timeout"] += 1
                    except Exception as e:
                        logger.error("Error mengambil hasil untuk %s: %s", url[:50], e)
                        results.append({
                            "url": url,
                            "success": False,
                            "error": str(e),
                        })
                        self.stats["failed"] += 1
        else:
            for url in urls:
                result = self._run_single(url)
                results.append(result)

        return results

    def process_results(self, results: List[Dict], field: str = "href") -> List[Dict]:
        """
        Convenience method: ambil URL dari hasil pencarian dan proses.

        Args:
            results: List hasil pencarian (dari search_dork).
            field: Field yang berisi URL (default: 'href').

        Returns:
            List hasil post-processing.
        """
        urls = [r.get(field, "") for r in results if r.get(field)]
        return self.process(urls)

    def summary(self) -> str:
        """Kembalikan ringkasan statistik."""
        return (
            f"Post-Processing: {self.stats['total']} total | "
            f"{self.stats['success']} success | "
            f"{self.stats['failed']} failed | "
            f"{self.stats['timeout']} timeout"
        )


# ── Convenience functions ──────────────────────────────────────────────

def extract_urls(results: List[Dict], field: str = "href") -> List[str]:
    """Ekstrak URL dari hasil pencarian dengan validasi."""
    urls = []
    for r in results:
        url = r.get(field, "")
        if isinstance(url, str) and url.strip():
            urls.append(url)
    return urls


def extract_vulnerable_urls(
    results: List[Dict],
    filter_arg: str = "wordpress",
    wordlist_dir: str = "wordlists",
) -> List[str]:
    """Ekstrak URL dari hasil yang rentan saja."""
    try:
        from core.filter_vuln import filter_vulnerable
        vuln, safe, _ = filter_vulnerable(results, filter_arg=filter_arg, wordlist_dir=wordlist_dir)
        urls = []
        for r in vuln:
            href = r.get("href", "")
            if isinstance(href, str) and href.strip():
                urls.append(href)
        return urls
    except ImportError:
        logger.warning("core.filter_vuln tidak tersedia, mengembalikan semua URL")
        return extract_urls(results)
    except Exception as e:
        logger.error("Gagal mengekstrak URL rentan: %s", e)
        return []


def run_command(
    command: str,
    urls: List[str],
    parallel: int = 1,
    timeout: int = 30,
) -> List[Dict]:
    """
    Convenience function: jalankan command untuk daftar URL.

    Args:
        command: Template command (gunakan {} untuk URL).
        urls: Daftar URL.
        parallel: Jumlah proses paralel.
        timeout: Batas waktu per perintah.

    Returns:
        List hasil untuk setiap URL.
    """
    processor = PostProcessor(command, parallel=parallel, timeout=timeout)
    return processor.process(urls)
