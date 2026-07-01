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
            # Bangun perintah
            cmd = self.command.replace("{}", shlex.quote(url))

            # Jalankan
            process = subprocess.run(
                cmd,
                shell=True, # nosec B602
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
            logger.error("Error menjalankan command untuk %s: %s", url, e)
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
                        logger.error("Timeout menunggu hasil untuk %s", url)
                        results.append({
                            "url": url,
                            "success": False,
                            "error": "Future timeout",
                        })
                        self.stats["timeout"] += 1
                    except Exception as e:
                        logger.error("Error mengambil hasil untuk %s: %s", url, e)
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
    """Ekstrak URL dari hasil pencarian."""
    return [r.get(field, "") for r in results if r.get(field)]


def extract_vulnerable_urls(
    results: List[Dict],
    filter_arg: str = "wordpress",
    wordlist_dir: str = "wordlists",
) -> List[str]:
    """Ekstrak URL dari hasil yang rentan saja."""
    try:
        from atdork.core.filter_vuln import filter_vulnerable
        vuln, safe, _ = filter_vulnerable(results, filter_arg=filter_arg, wordlist_dir=wordlist_dir)
        return [r.get("href", "") for r in vuln if r.get("href")]
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
