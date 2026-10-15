"""
Atdork – Professional Logging Setup
Menyediakan konfigurasi logger terpusat dengan rotasi file.
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional


# Konstanta default
DEFAULT_LOG_FILE = "atdork.log"
DEFAULT_MAX_BYTES = 1_000_000   # 1 MB
DEFAULT_BACKUP_COUNT = 3

# Format standar
CONSOLE_FORMAT = "%(message)s"
FILE_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
FILE_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Pustaka pihak ketiga yang berisik di level INFO/DEBUG (mis. primp menulis
# "response: <url> <status>" untuk setiap request HTTP).
NOISY_LOGGERS = frozenset({
    "primp",
    "ddgs",
    "httpx",
    "httpcore",
    "urllib3",
    "requests",
    "hickory_net",
})


class ConsoleNoiseFilter(logging.Filter):
    """Suppress third-party INFO/DEBUG chatter on the console only.

    Warnings and errors from these loggers still pass, and the full
    messages remain in the log file (the filter is attached to the
    console handler, not to the loggers themselves).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        top_level = record.name.split(".", 1)[0]
        if top_level in NOISY_LOGGERS:
            return record.levelno >= logging.WARNING
        return True


def setup_logging(
    debug: bool = False,
    log_file: Optional[str] = DEFAULT_LOG_FILE,
    console_level: Optional[int] = None,
    file_level: Optional[int] = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
) -> logging.Logger:
    """
    Konfigurasi root logger dengan console dan rotating file handler.

    Args:
        debug: Jika True, set level konsol ke DEBUG; jika False, konsol ke INFO.
        log_file: Path file log (None = tidak menulis ke file).
        console_level: Level eksplisit untuk console (menggantikan debug flag).
        file_level: Level untuk file handler (default DEBUG).
        max_bytes: Maksimum ukuran file log sebelum rotasi.
        backup_count: Jumlah file backup yang disimpan.

    Returns:
        Root logger yang sudah dikonfigurasi.

    Contoh:
        >>> setup_logging(debug=True, log_file="scan.log")
        >>> logging.info("Ini info")
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # tangkap semua level, filter di handler

    # Hindari penambahan handler ganda jika fungsi dipanggil ulang
    if root.handlers:
        root.handlers.clear()

    # ── Console Handler ─────────────────────────────────────────────────
    if console_level is None:
        console_level = logging.DEBUG if debug else logging.INFO

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(logging.Formatter(CONSOLE_FORMAT))
    # Redam chatter pihak ketiga di console (tetap utuh di file log).
    # Pada mode DEBUG kita sengaja membiarkannya lewat untuk troubleshooting.
    if console_level > logging.DEBUG:
        console_handler.addFilter(ConsoleNoiseFilter())
    root.addHandler(console_handler)

    # ── File Handler (Rotating) ─────────────────────────────────────────
    if log_file:
        # Pastikan direktori ada
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        if file_level is None:
            file_level = logging.DEBUG

        try:
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setLevel(file_level)
            file_handler.setFormatter(
                logging.Formatter(FILE_FORMAT, datefmt=FILE_DATE_FORMAT)
            )
            root.addHandler(file_handler)
        except (OSError, PermissionError) as e:
            # Fallback: hanya console logging
            root.warning("Cannot open log file %s: %s", log_file, e)

    return root
