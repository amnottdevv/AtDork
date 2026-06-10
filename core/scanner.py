import time
import logging
from ddgs import DDGS
from core.user_agents_managements import get_random_user_agent

logger = logging.getLogger(__name__)


def search_dork(
    query: str,
    max_results: int = 20,
    timeout: int = 10,
    retries: int = 2,
    delay: float = 0,
    proxy_manager=None,          # objek ProxyManager
    region: str = "us-en",
    safesearch: str = "moderate",
    timelimit: str = None,
    backend: str = "auto",
    user_agent: str = None,
) -> list:
    """
    Jalankan pencarian dork dengan dukungan rotasi proxy.

    Jika proxy_manager disediakan, akan mengambil proxy dari pool setiap percobaan.
    """
    if user_agent is None:
        user_agent = get_random_user_agent()
        logger.debug(f"Using random UA: {user_agent[:50]}...")

    last_error = None
    current_proxy = None

    for attempt in range(retries + 1):
        # Ambil proxy dari manager (jika ada)
        if proxy_manager:
            current_proxy = proxy_manager.get_proxy()  # bisa None (langsung)
            logger.debug(f"Menggunakan proxy: {current_proxy}")
        else:
            current_proxy = None

        try:
            if attempt > 0 and delay > 0:
                time.sleep(delay)

            # Buat instance DDGS dengan proxy terpilih
            ddgs = DDGS(timeout=timeout, proxy=current_proxy)

            # Set User-Agent
            try:
                if hasattr(ddgs, 'session') and ddgs.session:
                    ddgs.session.headers.update({"User-Agent": user_agent})
                else:
                    ddgs.headers = {"User-Agent": user_agent}
            except Exception as e:
                logger.debug(f"Tidak bisa set UA header: {e}")

            with ddgs:
                results = list(
                    ddgs.text(
                        query,
                        region=region,
                        safesearch=safesearch,
                        timelimit=timelimit,
                        max_results=max_results,
                        backend=backend,
                    )
                )
            if delay > 0:
                time.sleep(delay)

            # Sukses, laporkan ke proxy manager
            if proxy_manager:
                proxy_manager.report_success(current_proxy)
            return results

        except Exception as e:
            last_error = e
            logger.debug(f"Attempt {attempt+1} failed with proxy {current_proxy}: {e}")
            # Jika proxy gagal, laporkan
            if proxy_manager and current_proxy:
                proxy_manager.report_failure(current_proxy)

            if attempt < retries:
                backoff = 2 ** attempt
                logger.debug(f"Retrying in {backoff}s...")
                time.sleep(backoff)
                # Ganti UA untuk variasi
                user_agent = get_random_user_agent()

    raise RuntimeError(
        f"Gagal mengambil hasil setelah {retries} percobaan: {last_error}"
    )