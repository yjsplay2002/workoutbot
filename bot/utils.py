import time
from typing import Dict

# Rate limiter: chat_id -> last analysis timestamp
_last_analysis: Dict[int, float] = {}
RATE_LIMIT_SECONDS = 30


def check_rate_limit(chat_id: int) -> bool:
    """Return True if allowed, False if rate limited."""
    now = time.time()
    last = _last_analysis.get(chat_id, 0)
    if now - last < RATE_LIMIT_SECONDS:
        return False
    _last_analysis[chat_id] = now
    return True


def format_history_summary(records: list) -> str:
    if not records:
        return ""
    lines = []
    for r in records:
        lines.append(f"- {r['date']}: {r.get('structured_md', '')[:200]}")
    return "\n".join(lines)


def escape_markdown(text: str) -> str:
    """Light escape for Telegram Markdown v1 — only escape outside of formatting."""
    # We use Markdown parse mode, so we just return as-is and let Telegram handle it.
    # If issues arise, switch to HTML parse mode.
    return text
