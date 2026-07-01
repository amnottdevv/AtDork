"""
AtDork – Notification Module (core/notification.py)
Mengirim notifikasi ke Discord, Slack, atau Telegram.

Usage:
    from atdork.core.notification import send_notification, send_batch_summary

    send_notification("discord:https://hooks.discord.com/...", "Hello World")
    send_batch_summary(batch_results, "slack:https://hooks.slack.com/...")
"""

import json
import logging
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# Timeout for webhook requests (seconds)
WEBHOOK_TIMEOUT = 10

# Map platform prefix to its display name
PLATFORM_NAMES = {
    "discord": "Discord",
    "slack": "Slack",
    "telegram": "Telegram",
}


def _parse_target(target: str) -> tuple[str, str]:
    """
    Parse a target string of the form '<platform>:<webhook_url>'.

    Returns:
        (platform, webhook_url) tuple.
    """
    if ":" not in target:
        raise ValueError(
            f"Invalid notification target: {target}. "
            "Format: <platform>:<webhook_url> (e.g., discord:https://hooks.discord.com/...)"
        )
    platform, url = target.split(":", 1)
    platform = platform.strip().lower()
    url = url.strip()
    if platform not in PLATFORM_NAMES:
        raise ValueError(
            f"Unsupported platform '{platform}'. Supported: {', '.join(PLATFORM_NAMES.keys())}"
        )
    if not url.startswith("http"):
        raise ValueError(f"Invalid webhook URL: {url}")
    return platform, url


def _send_discord(webhook_url: str, message: str) -> bool:
    """Send a message to a Discord webhook."""
    payload = {"content": message[:2000]}  # Discord limit
    try:
        resp = requests.post(webhook_url, json=payload, timeout=WEBHOOK_TIMEOUT)
        if resp.status_code == 204:
            logger.info("Discord notification sent successfully")
            return True
        logger.warning("Discord returned %d: %s", resp.status_code, resp.text)
        return False
    except Exception as e:
        logger.error("Failed to send Discord notification: %s", e)
        return False


def _send_slack(webhook_url: str, message: str) -> bool:
    """Send a message to a Slack webhook."""
    payload = {"text": message}
    try:
        resp = requests.post(webhook_url, json=payload, timeout=WEBHOOK_TIMEOUT)
        if resp.status_code == 200:
            logger.info("Slack notification sent successfully")
            return True
        logger.warning("Slack returned %d: %s", resp.status_code, resp.text)
        return False
    except Exception as e:
        logger.error("Failed to send Slack notification: %s", e)
        return False


def _send_telegram(webhook_url: str, message: str) -> bool:
    """
    Send a message to a Telegram bot.

    The webhook_url should be the bot token (e.g., '123456:ABC').
    We also need a chat_id, so the format is:
        telegram:<bot_token>/<chat_id>
    """
    parts = webhook_url.split("/")
    if len(parts) != 2:
        raise ValueError(
            "Telegram target must be 'telegram:<bot_token>/<chat_id>'"
        )
    bot_token, chat_id = parts
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message[:4096],  # Telegram limit
        "parse_mode": "Markdown",
    }
    try:
        resp = requests.post(url, json=payload, timeout=WEBHOOK_TIMEOUT)
        if resp.status_code == 200:
            logger.info("Telegram notification sent successfully")
            return True
        logger.warning("Telegram returned %d: %s", resp.status_code, resp.text)
        return False
    except Exception as e:
        logger.error("Failed to send Telegram notification: %s", e)
        return False


# ── Public API ────────────────────────────────────────────────────────

def send_notification(target: str, message: str) -> bool:
    """
    Send a plain-text message to a notification target.

    Args:
        target: String like 'discord:https://hooks.discord.com/...'
        message: The message to send.

    Returns:
        True if the notification was sent successfully, False otherwise.
    """
    try:
        platform, url = _parse_target(target)
    except ValueError as e:
        logger.error(str(e))
        return False

    if platform == "discord":
        return _send_discord(url, message)
    elif platform == "slack":
        return _send_slack(url, message)
    elif platform == "telegram":
        try:
            return _send_telegram(url, message)
        except ValueError as e:
            logger.error(str(e))
            return False
    return False


def send_batch_summary(
    batch_results: Dict[str, List[Dict]],
    target: str,
    *,
    vulnerable_only: bool = False,
    total_hits: Optional[int] = None,
    query_count: Optional[int] = None,
) -> bool:
    """
    Send a batch summary notification.

    Args:
        batch_results: Dictionary {query: [list of result dicts]}.
        target: Notification target string.
        vulnerable_only: If True, only include queries that have results.
        total_hits: Override total number of results (optional).
        query_count: Override total number of queries (optional).

    Returns:
        True if successful.
    """
    try:
        platform, url = _parse_target(target)
    except ValueError as e:
        logger.error(str(e))
        return False

    # Build summary
    total = total_hits or sum(len(v) for v in batch_results.values())
    qcount = query_count or len(batch_results)

    lines = [
        f"📊 **AtDork Batch Complete**",
        f"• Queries: {qcount}",
        f"• Total results: {total}",
    ]

    if vulnerable_only:
        # Only show queries that actually returned results
        active = {q: r for q, r in batch_results.items() if r}
        if active:
            lines.append("• Queries with results:")
            for q, res in list(active.items())[:10]:  # limit to 10
                lines.append(f"  - `{q[:80]}`: {len(res)} results")
            if len(active) > 10:
                lines.append(f"  ... and {len(active) - 10} more")
        else:
            lines.append("• No vulnerable results found.")
    else:
        lines.append("• All queries completed successfully.")

    message = "\n".join(lines)

    if platform == "discord":
        return _send_discord(url, message)
    elif platform == "slack":
        return _send_slack(url, message)
    elif platform == "telegram":
        try:
            return _send_telegram(url, message)
        except ValueError as e:
            logger.error(str(e))
            return False
    return False
