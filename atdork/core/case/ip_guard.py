"""
Atdork – IP Leak Guard (core/case/ip_guard.py)
Mendeteksi kebocoran IP asli saat menggunakan proxy/Tor.

Dilengkapi try‑except di semua method kritis agar error terlihat jelas.
"""

import requests
import logging
from typing import Optional, List, Tuple

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

    # ── Helper ──────────────────────────────────────────────────────────
    @staticmethod
    def get_public_ip(proxies: Optional[dict] = None, timeout: int = 5) -> Optional[str]:
        """
        Ambil IP publik yang terlihat oleh internet.
        """
        try:
            resp = requests.get(
                "https://httpbin.org/ip",
                proxies=proxies,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict) or "origin" not in data:
                logger.warning("Respons httpbin.org tidak valid: %s", data)
                return None
            return data["origin"].split(",")[0].strip()
        except requests.exceptions.Timeout:
            logger.error("Timeout saat mengambil IP publik (timeout=%ds)", timeout)
        except requests.exceptions.ConnectionError as e:
            logger.error("Gagal koneksi ke httpbin.org: %s", e)
        except requests.exceptions.HTTPError as e:
            logger.error("HTTP error dari httpbin.org: %s", e)
        except Exception as e:
            logger.error("Error tidak terduga saat mengambil IP publik: %s", e)
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
                self.baseline_proxy_ip = ip
                logger.info("IP baseline (via proxy): %s", ip)
                if ip == self.real_ip:
                    logger.warning("IP via proxy SAMA dengan IP asli – kemungkinan proxy tidak berfungsi!")
                    self.leak_detected = True
                    self.leak_details.append("Proxy returned same IP as real IP (proxy not working)")
            else:
                logger.warning("Tidak dapat menetapkan IP baseline – proxy mungkin mati")
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
                warnings.append("Tidak dapat memeriksa IP (network error)")
                return False, warnings

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
            return f"""
{'='*60}
  ❌  IP LEAK DETECTED – PROGRAM STOPPED
{'='*60}

  Your real IP address has been exposed to the public.

  ┌─────────────────────────────────────────────────────────┐
  │  Your IP (real):    {self.real_ip:<40} │
  │  Expected IP:       {self.baseline_proxy_ip or 'N/A':<40} │
  │  Details:           {self.leak_details[0] if self.leak_details else 'Unknown':<40} │
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
