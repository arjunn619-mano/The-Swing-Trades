"""Failure/health alerts via Telegram (Guardrail 8: the worker must shout when it fails).
`http_post` is injectable for offline tests. Returns True on success, False otherwise —
never raises, so alerting can't itself break the scan."""
from __future__ import annotations

from typing import Callable, Optional


def send_telegram_alert(
    message: str,
    *,
    bot_token: Optional[str],
    chat_id: Optional[str],
    http_post: Optional[Callable] = None,
    timeout: int = 15,
) -> bool:
    if not bot_token or not chat_id:
        return False
    if http_post is None:
        import requests  # lazy import

        http_post = requests.post
    try:
        resp = http_post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": message},
            timeout=timeout,
        )
        resp.raise_for_status()
        return True
    except Exception:
        return False
