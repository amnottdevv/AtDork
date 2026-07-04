"""
Atdork – IP Leak Guard (core/case/ip_guard.py)
Mendeteksi kebocoran IP asli saat menggunakan proxy/Tor.

Dilengkapi try‑except di semua method kritis agar error terlihat jelas.

FIX (v2):
- get_public_ip() sekarang mencoba beberapa provider IP-check secara
  berurutan (bukan cuma httpbin.org). Fitur --ip-guard adalah lapisan
  keamanan utama; satu provider eksternal yang down/rate-limit tidak
  boleh membuat seluruh deteksi kebocoran gagal (false "leak").
- Semua method yang membaca/menulis state (leak_detected, leak_details,
  baseline_proxy_ip) sekarang dilindungi threading.Lock(), karena
  IPGuard bisa dipakai bersamaan oleh banyak thread saat --concurrency > 1.
"""

import requests
import logging
import threading
from typing import Optional, List, Tuple, Callable

logger = logging.getLogger(__name__)

# Header yang bisa membocorkan IP
SUSPICIOUS_HEADERS = [
    "X-Forwarded-For",
    "X-Real-IP",
    "X-Client-IP",
    "X-Originating-IP",
    "X-Remote-IP",
    "X-Host",
    "X-ProxyUser-IP",
    "CF-Connecting-IP",
    "True-Client-IP",
    "Forwarded",
    "Via",
]


def _parse_httpbin(data: str) -> Optional[str]:
    """Parser untuk https://httpbin.org/ip -> {"origin": "1.2.3.4"}"""
    import json
    obj = json.loads(data)
    if not isinstance(obj, dict) or "origin" not in obj:
        return None
    return obj["origin"].split(",")[0].strip()


def _parse_ipify(data: str) -> Optional[str]:
    """Parser untuk https://api.ipify.org?format=json -> {"ip": "1.2.3.4"}"""
    import json
    obj = json.loads(data)
    if not isinstance(obj, dict) or "ip" not in obj:
        return None
    return str(obj["ip"]).strip()


def _parse_plaintext(data: str) -> Optional[str]:
    """Parser untuk endpoint yang mengembalikan IP polos (icanhazip.com, ident.me, dll)."""
    ip = data.strip().split(",")[0].strip()
    return ip or None



_IP_CHECK_PROVIDERS: List[Tuple[str, Callable[[str], Optional[str]]]] = [
    ("https://httpbin.org/ip", _parse_httpbin),
    ("https://api.ipify.org?format=json", _parse_ipify),
    ("https://icanhazip.com", _parse_plaintext),
    ("https://ident.me", _parse_plaintext),
]


class IPGuardError(Exception):
    """Exception khusus untuk IPGuard."""
    pass


class IPGuard:
    """
    Melindungi privasi pengguna dengan mendeteksi kebocoran IP.

    Args:
        real_ip: IP asli pengguna (didapat sebelum menggunakan proxy).
        strict: Jika True, hentikan program saat kebocoran terdeteksi.
    """

    def __init__(self, real_ip: str, strict: bool = True):
        if not real_ip:
            raise IPGuardError("real_ip tidak boleh kosong")
        self.real_ip = real_ip
        self.strict = strict
        self.baseline_proxy_ip: Optional[str] = None
        self.leak_detected: bool = False
        self.leak_details: List[str] = []
        # FIX: lock untuk melindungi state di atas dari race condition
        # saat IPGuard dipakai dari banyak thread (--concurrency > 1).
        self._lock = threading.Lock()

    # ── Helper ──────────────────────────────────────────────────────────
    @staticmethod
    def get_public_ip(proxies: Optional[dict] = None, timeout: int = 5) -> Optional[str]:
        """
        Ambil IP publik yang terlihat oleh internet.

        FIX: Mencoba beberapa provider secara berurutan (httpbin.org, ipify,
        icanhazip.com, ident.me). Kembalikan hasil provider pertama yang
        berhasil. Kalau semua provider gagal, baru kembalikan None.
        """
        last_error: Optional[str] = None
        for url, parser in _IP_CHECK_PROVIDERS:
            try:
                resp = requests.get(url, proxies=proxies, timeout=timeout)
                resp.raise_for_status()
                ip = parser(resp.text)
                if ip:
                    logger.debug("IP publik berhasil didapat dari %s", url)
                    return ip
                logger.warning("Respons tidak valid dari %s: %s", url, resp.text[:100])
                last_error = f"Respons tidak valid dari {url}"
            except requests.exceptions.Timeout:
                logger.debug("Timeout saat menghubungi %s (timeout=%ds)", url, timeout)
                last_error = f"Timeout dari {url}"
            except requests.exceptions.ConnectionError as e:
                logger.debug("Gagal koneksi ke %s: %s", url, e)
                last_error = f"Gagal koneksi ke {url}: {e}"
            except requests.exceptions.HTTPError as e:
                logger.debug("HTTP error dari %s: %s", url, e)
                last_error = f"HTTP error dari {url}: {e}"
            except Exception as e:
                logger.debug("Error tidak terduga dari %s: %s", url, e)
                last_error = f"Error tidak terduga dari {url}: {e}"
            # Provider ini gagal, lanjut coba provider berikutnya

        logger.error(
            "Semua provider IP-check gagal (%d dicoba). Terakhir: %s",
            len(_IP_CHECK_PROVIDERS), last_error,
        )
        return None

    @staticmethod
    def inspect_response_headers(headers: dict, real_ip: str) -> List[str]:
        """
        Periksa header respons dari backend.
        Kembalikan daftar header yang mengandung IP asli pengguna.
        """
        if not isinstance(headers, dict):
            return []
        leaks = []
        for header in SUSPICIOUS_HEADERS:
            try:
                value = headers.get(header)
                if value and real_ip in str(value):
                    leaks.append(f"{header}: {value}")
            except Exception as e:
                logger.debug("Gagal memeriksa header %s: %s", header, e)
        return leaks

    # ── Pemeriksaan ────────────────────────────────────────────────────
    def establish_baseline(self, proxy_url: Optional[str] = None) -> Optional[str]:
        """
        Tetapkan IP baseline (IP yang terlihat melalui proxy).
        """
        proxies = None
        if proxy_url:
            proxies = {"http": proxy_url, "https": proxy_url}

        try:
            ip = self.get_public_ip(proxies)
            if ip:
                with self._lock:
                    self.baseline_proxy_ip = ip
                    logger.info("IP baseline (via proxy): %s", ip)
                    if ip == self.real_ip:
                        logger.warning("IP via proxy SAMA dengan IP asli – kemungkinan proxy tidak berfungsi!")
                        self.leak_detected = True
                        self.leak_details.append("Proxy returned same IP as real IP (proxy not working)")
            else:
                logger.warning("Tidak dapat menetapkan IP baseline – semua provider IP-check gagal atau proxy mati")
            return ip
        except Exception as e:
            logger.error("Error di establish_baseline: %s", e)
            return None

    def check(self, proxy_url: Optional[str] = None) -> Tuple[bool, List[str]]:
        """
        Periksa apakah IP saat ini bocor dibandingkan baseline.
        Returns (is_safe, warnings).
        """
        warnings = []
        proxies = None
        if proxy_url:
            proxies = {"http": proxy_url, "https": proxy_url}

        try:
            current_ip = self.get_public_ip(proxies)

            if current_ip is None:
                warnings.append("Tidak dapat memeriksa IP (semua provider IP-check gagal / network error)")
                return False, warnings

            with self._lock:
                # Bandingkan dengan baseline
                if self.baseline_proxy_ip and current_ip != self.baseline_proxy_ip:
                    if current_ip == self.real_ip:
                        self.leak_detected = True
                        msg = f"IP bocor! Terlihat: {current_ip} (IP asli), seharusnya: {self.baseline_proxy_ip}"
                        self.leak_details.append(msg)
                        warnings.append(msg)
                        return False, warnings
                    else:
                        warnings.append(f"IP berubah dari baseline: {current_ip} (mungkin proxy berbeda)")

                # Bandingkan langsung dengan IP asli
                if current_ip == self.real_ip:
                    self.leak_detected = True
                    msg = f"IP asli terlihat oleh publik: {current_ip}"
                    self.leak_details.append(msg)
                    warnings.append(msg)
                    return False, warnings

                return True, warnings

        except Exception as e:
            logger.error("Error di check(): %s", e)
            return False, [f"Pengecekan IP gagal: {e}"]

    # ── Pesan Error ────────────────────────────────────────────────────
    def panic_message(self) -> str:
        """Pesan error lengkap saat kebocoran terdeteksi."""
        try:
            with self._lock:
                baseline = self.baseline_proxy_ip or "N/A"
                detail = self.leak_details[0] if self.leak_details else "Unknown"
            return f"""
{'='*60}
  ❌  IP LEAK DETECTED – PROGRAM STOPPED
{'='*60}

  Your real IP address has been exposed to the public.

  ┌─────────────────────────────────────────────────────────┐
  │  Your IP (real):    {self.real_ip:<40} │
  │  Expected IP:       {baseline:<40} │
  │  Details:           {detail:<40} │
  └─────────────────────────────────────────────────────────┘

  What happened:
  AtDork detected that your real IP address was visible to
  external servers while using proxy/Tor. This could happen if:
  - All proxies failed and a direct connection was made
  - The proxy is not anonymous (transparent proxy)
  - DNS leak occurred (your DNS request bypassed the proxy)

  Immediate action recommended:
  1. Check your proxy list (proxies.txt) – are all proxies alive?
  2. Verify Tor is running if using --tor
  3. Use SOCKS5h proxy to prevent DNS leaks
  4. Check your firewall settings
  5. Consider using a VPN as additional layer

  Your privacy may have been compromised.
  Consider changing your IP address before continuing.

  ⚠️  AtDork has stopped to prevent further exposure.
{'='*60}
"""
        except Exception as e:
            return f"IP LEAK DETECTED – Real IP: {self.real_ip}. Error menampilkan pesan: {e}"
