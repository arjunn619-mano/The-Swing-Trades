"""Real HTTP transport for the news adapters. Kept behind the injected http_get seam so the
adapters stay testable offline and this is the ONE place to swap when the job moves to the Oracle
VM IP. Never raises — a transport failure becomes a FetchResult(error=...) the health gauntlet reports."""
from __future__ import annotations

from .sources.base import FetchResult


def requests_get(url: str, headers=None, params=None, timeout: int = 20) -> FetchResult:
    import requests

    try:
        r = requests.get(url, headers=headers, params=params, timeout=timeout)
        return FetchResult(r.status_code, r.headers.get("Content-Type", ""), r.text)
    except requests.RequestException as e:  # timeout / connection / blocked
        return FetchResult(0, "", "", error=str(e))
