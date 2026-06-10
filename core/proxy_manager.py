"""
Atdork - Proxy Manager (Upgraded)
Rotasi proxy dengan validasi, strict mode, statistik, dan health check.
"""

import re
import time
import threading
import socket
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Pola validasi: harus punya skema://host:port
PROXY_PATTERN = re.compile(
    r'^(http|https|socks4|socks5|socks5h)://'
    r'([^:/]+)'
    r':(\d{1,5})$'
)


def is_valid_proxy(proxy: str) -> bool:
    """Memvalidasi format proxy: skema://host:port."""
    if not proxy:
        return False
    m = PROXY_PATTERN.match(proxy)
    if not m:
        return False
    port = int(m.group(3))
    return 1 <= port <= 65535


def test_proxy(proxy: str, timeout: float = 2.0) -> bool:
    """
    Tes apakah proxy bisa digunakan dengan koneksi socket sederhana.
    Untuk SOCKS tidak bisa di-socket test langsung, jadi kita parse host:port saja.
    """
    if not is_valid_proxy(proxy):
        return False
    try:
        parsed = urlparse(proxy)
        host = parsed.hostname
        port = parsed.port
        if not host or not port:
            return False
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except Exception:
        return False


class ProxyManager:
    """
    Mengelola pool proxy dengan rotasi, cooldown, auto-removal, dan statistik.

    Args:
        proxies: daftar awal proxy (string URL)
        cooldown_seconds: lama cooldown setelah gagal (default 60)
        strict: jika True, tidak akan fallback ke koneksi langsung (None) saat semua proxy down
        max_failures: jumlah kegagalan berturut-turut sebelum proxy dihapus permanen (0 = tidak pernah hapus)
    """

    def __init__(
        self,
        proxies: list,
        cooldown_seconds: int = 60,
        strict: bool = False,
        max_failures: int = 3,
    ):
        # Filter hanya proxy valid
        valid = [p for p in proxies if is_valid_proxy(p)]
        invalid_count = len(proxies) - len(valid)
        if invalid_count > 0:
            logger.warning(f"{invalid_count} proxy tidak valid dan diabaikan.")

        self._proxies = valid
        self._lock = threading.Lock()
        self._index = 0
        self._cooldown = cooldown_seconds
        self._banned_until = {}   # proxy -> timestamp
        self._strict = strict
        self._max_failures = max_failures

        # Statistik
        self._stats = {}          # proxy -> {'success': int, 'failure': int, 'consecutive_fails': int}

        if not self._proxies and strict:
            raise ValueError("strict=True tetapi tidak ada proxy valid tersedia.")

        if not self._proxies:
            logger.warning("ProxyManager dibuat tanpa proxy valid, akan menggunakan koneksi langsung.")

    @property
    def proxies(self) -> list:
        """Salinan daftar proxy aktif."""
        with self._lock:
            return list(self._proxies)

    @property
    def stats(self) -> dict:
        """Salinan statistik saat ini."""
        with self._lock:
            return dict(self._stats)

    def add_proxy(self, proxy: str):
        """Tambah proxy ke pool secara dinamis (jika valid dan belum ada)."""
        if not is_valid_proxy(proxy):
            logger.warning(f"Proxy tidak valid, diabaikan: {proxy}")
            return
        with self._lock:
            if proxy not in self._proxies:
                self._proxies.append(proxy)
                logger.info(f"Proxy ditambahkan: {proxy}")

    def remove_proxy(self, proxy: str):
        """Hapus proxy dari pool secara manual."""
        with self._lock:
            if proxy in self._proxies:
                self._proxies.remove(proxy)
                self._banned_until.pop(proxy, None)
                self._stats.pop(proxy, None)
                logger.info(f"Proxy dihapus: {proxy}")

    def _init_stats(self, proxy: str):
        if proxy and proxy not in self._stats:
            self._stats[proxy] = {'success': 0, 'failure': 0, 'consecutive_fails': 0}

    def get_proxy(self) -> str | None:
        """
        Ambil proxy berikutnya yang tidak sedang cooldown.
        Mengembalikan None jika semua proxy down (strict=False) atau raise jika strict=True.
        """
        with self._lock:
            if not self._proxies:
                if self._strict:
                    raise RuntimeError("Tidak ada proxy tersedia (strict mode).")
                return None

            now = time.time()
            # Coba putar sampai ketemu yang siap
            for _ in range(len(self._proxies)):
                proxy = self._proxies[self._index]
                self._index = (self._index + 1) % len(self._proxies)
                until = self._banned_until.get(proxy, 0)
                if now >= until:
                    return proxy

            # Semua proxy dalam cooldown
            if self._strict:
                raise RuntimeError("Semua proxy sedang dalam cooldown (strict mode).")
            return None  # fallback ke koneksi langsung

    def report_failure(self, proxy: str):
        """Catat kegagalan proxy, kenakan cooldown, dan hapus jika melebihi max_failures."""
        if proxy is None:
            return
        with self._lock:
            self._init_stats(proxy)
            self._stats[proxy]['failure'] += 1
            self._stats[proxy]['consecutive_fails'] += 1

            # Cooldown
            until = time.time() + self._cooldown
            self._banned_until[proxy] = until
            logger.debug(f"Proxy {proxy} cooldown sampai {until:.0f}")

            # Cek apakah harus dihapus permanen
            if self._max_failures > 0 and self._stats[proxy]['consecutive_fails'] >= self._max_failures:
                self._proxies.remove(proxy)
                self._banned_until.pop(proxy, None)
                del self._stats[proxy]
                logger.warning(f"Proxy {proxy} dihapus permanen setelah {self._max_failures} kegagalan berturut-turut.")

    def report_success(self, proxy: str):
        """Catat keberhasilan, reset cooldown & consecutive fails."""
        if proxy is None:
            return
        with self._lock:
            self._init_stats(proxy)
            self._stats[proxy]['success'] += 1
            self._stats[proxy]['consecutive_fails'] = 0
            self._banned_until.pop(proxy, None)

    def get_stats_summary(self) -> dict:
        """Kembalikan ringkasan statistik untuk logging/monitoring."""
        with self._lock:
            active = len(self._proxies)
            banned = len(self._banned_until)
            total_success = sum(s['success'] for s in self._stats.values())
            total_failure = sum(s['failure'] for s in self._stats.values())
            return {
                'active': active,
                'banned': banned,
                'total_success': total_success,
                'total_failure': total_failure,
            }


# ========== Helper untuk CLI ==========

def load_proxies_from_file(path: str) -> list[str]:
    """Baca file proxy (satu URL per baris), skip komentar '#' dan baris kosong."""
    proxies = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            proxies.append(line)
    return proxies


def load_proxies_from_string(proxies_str: str, separator: str = ",") -> list[str]:
    """Parse string proxy yang dipisahkan oleh separator (default koma)."""
    return [p.strip() for p in proxies_str.split(separator) if p.strip()]


def _check_tor_socks_port(host="127.0.0.1", port=9050, timeout=1.0) -> bool:
    """Cek apakah Tor SOCKS5 port tersedia."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def create_proxy_manager(
    proxy_arg: str | None = None,
    proxy_file: str | None = None,
    enable_tor: bool = False,
    cooldown: int = 60,
    strict: bool = False,
    max_failures: int = 3,
) -> ProxyManager:
    """
    Factory untuk membuat ProxyManager dari berbagai sumber CLI.

    Sumber (digabung, duplikat dihilangkan):
    1. --proxy-file
    2. --proxy (koma)
    3. Tor (jika diminta dan port 9050 tersedia)
    """
    proxies = set()

    if proxy_file:
        try:
            file_proxies = load_proxies_from_file(proxy_file)
            proxies.update(file_proxies)
            logger.info(f"{len(file_proxies)} proxy dimuat dari {proxy_file}")
        except Exception as e:
            logger.error(f"Gagal membaca file proxy: {e}")

    if proxy_arg:
        string_proxies = load_proxies_from_string(proxy_arg)
        proxies.update(string_proxies)
        logger.info(f"{len(string_proxies)} proxy dari argumen --proxy")

    if enable_tor:
        tor_proxy = "socks5h://127.0.0.1:9050"
        if _check_tor_socks_port():
            proxies.add(tor_proxy)
            logger.info("Tor SOCKS5 tersedia, ditambahkan ke pool.")
        else:
            logger.warning("Tor diaktifkan tetapi port 9050 tidak tersedia.")

    proxy_list = list(proxies)
    return ProxyManager(
        proxy_list,
        cooldown_seconds=cooldown,
        strict=strict,
        max_failures=max_failures,
    )