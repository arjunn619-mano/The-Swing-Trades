"""Thin HTTP client for the Dhan v2 *data* endpoints only (no order-routing surface).

Read-only by construction: this client exposes historical + quote and nothing that can
place a trade. `session` and `sleep` are injectable for offline unit tests."""
from __future__ import annotations

import time
from typing import Callable, Optional

from .historical import parse_historical_response
from .models import PriceBar

BASE_URL = "https://api.dhan.co/v2"


class DhanDataClient:
    def __init__(
        self,
        access_token: str,
        client_id: str,
        *,
        session=None,
        base_url: str = BASE_URL,
        sleep: Callable[[float], None] = time.sleep,
        retries: int = 3,
        backoff: float = 1.0,
    ) -> None:
        if session is None:
            import requests  # lazy import

            session = requests.Session()
        self.access_token = access_token
        self.client_id = client_id
        self.session = session
        self.base_url = base_url.rstrip("/")
        self._sleep = sleep
        self._retries = retries
        self._backoff = backoff

    def _headers(self) -> dict[str, str]:
        return {
            "access-token": self.access_token,
            "client-id": self.client_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _post(self, path: str, body: dict) -> dict:
        last_err: Optional[Exception] = None
        for attempt in range(self._retries):
            try:
                resp = self.session.post(
                    self.base_url + path, json=body, headers=self._headers(), timeout=30
                )
                resp.raise_for_status()
                return resp.json()
            except Exception as err:  # network / HTTP / decode — retry with backoff
                last_err = err
                if attempt < self._retries - 1:
                    self._sleep(self._backoff * (attempt + 1))
        assert last_err is not None
        raise last_err

    def historical_daily(
        self,
        security_id: str,
        exchange_segment: str,
        from_date: str,
        to_date: str,
        instrument: str = "EQUITY",
    ) -> list[PriceBar]:
        body = {
            "securityId": str(security_id),
            "exchangeSegment": exchange_segment,
            "instrument": instrument,
            "expiryCode": 0,
            "oi": False,
            "fromDate": from_date,
            "toDate": to_date,  # non-inclusive per Dhan docs
        }
        return parse_historical_response(self._post("/charts/historical", body))

    def quote(self, instruments_by_segment: dict[str, list]) -> dict:
        """Raw /marketfeed/quote response. Pair with quotes.parse_quote_response(resp, date)."""
        return self._post("/marketfeed/quote", instruments_by_segment)
