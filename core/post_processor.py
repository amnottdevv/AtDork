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
import platform
from typing import List, Dict, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

logger = logging.getLogger(__name__)


_WINDOWS_SHELL_RISK_CHARS = ['&', '|', '>', '<', '^', '%']

# Characters that force us to go through a real shell. If the template has
# none of these we can pass the URL as a plain argv entry (shell=False) and be
# immune to command injection on every platform.
_SHELL_METACHARS = set("|&;<>()$`\n\r*?[]~")
_WINDOWS_SHELL_ONLY_METACHARS = set("%^!")

# Characters that cmd.exe still interprets even inside double quotes, so a URL
# containing them cannot be safely embedded in a shell command on Windows.
_WINDOWS_CMD_UNSAFE_CHARS = ['"', '%', '!', '\n', '\r']


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
            raise ValueError("Command must contain the '{}' placeholder for the URL")

        self.command = command
        self.parallel = max(1, parallel)
        self.timeout = timeout
        self.on_success = on_success
        self.on_error = on_error

        # FIX HIGH: Hanya pakai shell bila template memang butuh fitur shell
        # (pipe, redirect, glob, dsb). Template sederhana seperti "curl -I {}"
        # dijalankan tanpa shell sehingga URL tidak pernah di-parse oleh shell.
        self._is_windows = platform.system() == "Windows"
        metachars = set(_SHELL_METACHARS)
        if self._is_windows:
            metachars |= _WINDOWS_SHELL_ONLY_METACHARS
        self._needs_shell = any(ch in self.command for ch in metachars)

        if self._is_windows and self._needs_shell:
            template_risk = [c for c in _WINDOWS_SHELL_RISK_CHARS if c in self.command]
            logger.warning(
                "PostProcessor is running on Windows with a shell template. "
                "Command templates that use pipes/redirects must go through "
                "cmd.exe, and URLs containing %%, !, or \" cannot be escaped "
                "safely there — such URLs will be skipped. %s"
                "Use a simple command template without pipe/redirect on Windows, "
                "or run AtDork via WSL for stronger escaping guarantees.",
                (
                    f"Your command template itself contains shell characters ({', '.join(template_risk)}). "
                    if template_risk else ""
                ),
            )

        # Statistik
        self.stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "timeout": 0,
        }
        # FIX: stats di-update dari banyak thread (--exec-parallel) → lindungi.
        self._stats_lock = threading.Lock()

    def _bump(self, key: str, amount: int = 1) -> None:
        """Update statistik secara thread-safe."""
        with self._stats_lock:
            self.stats[key] += amount

    def _quote_for_shell(self, url: str) -> str:
        """Quote URL untuk dimasukkan ke template shell.

        POSIX memakai shlex.quote (aman). Windows (cmd.exe) tidak memahami
        single-quote POSIX; karakter yang tetap berbahaya di dalam double-quote
        (%, !, ") membuat URL tersebut tidak bisa diamankan → ditolak.
        """
        if self._is_windows:
            unsafe = [c for c in _WINDOWS_CMD_UNSAFE_CHARS if c in url]
            if unsafe:
                raise ValueError(
                    "URL contains characters that cannot be safely escaped for "
                    f"cmd.exe ({', '.join(repr(c) for c in unsafe)}); "
                    "refusing to run the shell command. Use a template without "
                    "pipes/redirects to run this URL safely."
                )
            return f'"{url}"'
        return shlex.quote(url)

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
                self._bump("failed")
                return result
            
            # FIX HIGH: Check for suspicious patterns that could bypass shlex.quote
            suspicious_chars = ['$', '`', '\n', '\r', '\0']
            if any(char in url for char in suspicious_chars):
                logger.warning(f"URL contains suspicious characters, skipping: {url[:50]}")
                result["error"] = "URL contains suspicious characters"
                self._bump("failed")
                return result

            if not self._needs_shell:
                # FIX HIGH: Tanpa shell, URL diteruskan sebagai satu argumen
                # (shell=False) → tidak bisa di-injeksi di platform manapun.
                argv = [
                    token.replace("{}", url)
                    for token in shlex.split(self.command, posix=not self._is_windows)
                ]
                logger.debug(
                    "Executing command without shell (URL length: %d chars)", len(url)
                )
                process = subprocess.run(
                    argv,
                    shell=False,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
            else:
                # Template butuh fitur shell → escaping yang sesuai per-OS.
                url_escaped = self._quote_for_shell(url)
                cmd = self.command.replace("{}", url_escaped)
                logger.debug(
                    "Executing command with shell (URL length: %d chars)", len(url)
                )
                process = subprocess.run(
                    cmd,
                    shell=True,  # nosec
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )

            result["returncode"] = process.returncode
            result["stdout"] = process.stdout.strip()
            result["stderr"] = process.stderr.strip()

            if process.returncode == 0:
                result["success"] = True
                self._bump("success")
                if self.on_success:
                    try:
                        self.on_success(url, result)
                    except Exception as e:
                        logger.error("Error in on_success callback: %s", e)
            else:
                self._bump("failed")
                result["error"] = f"Exit code: {process.returncode}"
                if self.on_error:
                    try:
                        self.on_error(url, result)
                    except Exception as e:
                        logger.error("Error in on_error callback: %s", e)

        except subprocess.TimeoutExpired:
            self._bump("timeout")
            result["error"] = f"Timeout after {self.timeout}s"
            if self.on_error:
                try:
                    self.on_error(url, result)
                except Exception as e:
                    logger.error("Error in on_error callback: %s", e)

        except Exception as e:
            self._bump("failed")
            result["error"] = str(e)
            logger.error("Error running command for %s: %s", url[:50], e)
            if self.on_error:
                try:
                    self.on_error(url, result)
                except Exception as e2:
                    logger.error("Error in on_error callback: %s", e2)

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
                        logger.error("Timeout waiting for results for %s", url[:50])
                        results.append({
                            "url": url,
                            "success": False,
                            "error": "Future timeout",
                        })
                        self._bump("timeout")
                    except Exception as e:
                        logger.error("Error getting results for %s: %s", url[:50], e)
                        results.append({
                            "url": url,
                            "success": False,
                            "error": str(e),
                        })
                        self._bump("failed")
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
        logger.warning("core.filter_vuln not available, returning all URLs")
        return extract_urls(results)
    except Exception as e:
        logger.error("Failed to extract vulnerable URLs: %s", e)
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
