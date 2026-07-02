# Notification System

## Introduction
The Notification System allows AtDork to send batch summaries and alerts to external messaging platforms. This is useful for automated workflows, team collaboration, and real‑time monitoring of OSINT campaigns without needing to manually check results.

## Functions
| Flag | Description |
|------|-------------|
| `--notify <platform>:<webhook>` | Send a batch summary to the specified platform. |
| `--notify-if-vuln` | Only send the notification if vulnerable results were found (requires `--filter-vuln`). |

**Supported platforms:**
- **Discord** – `discord:https://hooks.discord.com/api/webhooks/...`
- **Slack** – `slack:https://hooks.slack.com/services/...`
- **Telegram** – `telegram:<bot_token>/<chat_id>`

## Usage Examples
```bash
# Send a batch summary to Discord
atdork --batch-file dorks.txt -r 20 --notify "discord:https://hooks.discord.com/api/webhooks/xxx/yyy"

# Send to Slack only if vulnerable results are found
atdork -q "inurl:wp-content" -r 30 --filter-vuln wordpress \
  --notify "slack:https://hooks.slack.com/services/xxx/yyy/zzz" --notify-if-vuln

# Send to Telegram
atdork --batch-file dorks.txt -r 20 \
  --notify "telegram:123456789:ABCdefGHIjklMNOpqrsTUVwxyz/123456789"

# Full campaign with resilience, proxy, and Discord notification
atdork --batch-file dorks.txt --resilient --adaptive-delay \
  --proxy-file proxies.txt --strict --concurrency 3 \
  --notify "discord:https://hooks.discord.com/api/webhooks/xxx/yyy"

# Template scan with notification only for vulnerable findings
atdork --template sqli --target example.com -r 15 \
  --notify "slack:https://hooks.slack.com/services/xxx/yyy/zzz" --notify-if-vuln
```

## How It Works

1. **Platform Detection**  
   The target string (`discord:...`, `slack:...`, `telegram:...`) is parsed to determine the platform and webhook URL. If the format is invalid, a clear error message is displayed.

2. **Message Construction**  
   A summary message is built containing:
   - Total number of queries executed
   - Total number of results found
   - Optionally, a list of queries that returned vulnerable results (if `--notify-if-vuln` is active)

3. **Sending**  
   The message is sent via HTTP POST to the platform's webhook API:
   - **Discord** – JSON payload `{"content": "..."}` to the webhook URL.
   - **Slack** – JSON payload `{"text": "..."}` to the webhook URL.
   - **Telegram** – JSON payload `{"chat_id": "...", "text": "...", "parse_mode": "Markdown"}` to `https://api.telegram.org/bot<token>/sendMessage`.

4. **Conditional Notifications**  
   If `--notify-if-vuln` is set, the notification is only sent when at least one query returns vulnerable results (requires `--filter-vuln` to be active). If no vulnerabilities are found, the notification is silently skipped.

5. **Error Handling**  
   Network errors, invalid URLs, or platform-specific errors are logged and do not crash the main batch process. A warning is printed to the console if the notification fails.

## Example Notification Message

```text
📊 **AtDork Batch Complete**
• Queries: 25
• Total results: 142
• All queries completed successfully.
```
