import pytest

from swing_trades.data_layer.dhan_client import DhanDataClient


class FakeResp:
    def __init__(self, payload, status=200):
        self._p = payload
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    def json(self):
        return self._p


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append((url, json, headers))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_historical_daily_sends_headers_and_parses():
    payload = {"open": [100], "high": [101], "low": [99], "close": [100.5],
               "volume": [10], "timestamp": [1704067200]}
    sess = FakeSession([FakeResp(payload)])
    client = DhanDataClient("JWT", "C1", session=sess)
    bars = client.historical_daily("2885", "NSE_EQ", "2024-01-01", "2024-01-02")
    assert len(bars) == 1 and bars[0].close == 100.5
    url, body, headers = sess.calls[0]
    assert url.endswith("/charts/historical")
    assert headers["access-token"] == "JWT" and headers["client-id"] == "C1"
    assert body["securityId"] == "2885" and body["exchangeSegment"] == "NSE_EQ"
    assert body["instrument"] == "EQUITY"


def test_quote_returns_raw_data():
    payload = {"data": {"NSE_EQ": {"2885": {"ohlc": {"open": 1, "high": 2, "low": 0.5,
               "close": 1.5}, "volume": 5}}}, "status": "success"}
    sess = FakeSession([FakeResp(payload)])
    client = DhanDataClient("JWT", "C1", session=sess)
    out = client.quote({"NSE_EQ": [2885]})
    assert out["data"]["NSE_EQ"]["2885"]["volume"] == 5


def test_post_retries_then_succeeds():
    payload = {"open": [1], "high": [1], "low": [1], "close": [1],
               "volume": [1], "timestamp": [1704067200]}
    sess = FakeSession([RuntimeError("transient"), FakeResp(payload)])
    client = DhanDataClient("JWT", "C1", session=sess, sleep=lambda _s: None)
    bars = client.historical_daily("1", "NSE_EQ", "2024-01-01", "2024-01-02")
    assert len(bars) == 1
    assert len(sess.calls) == 2  # retried once after the transient failure


class FakeHTTPError(Exception):
    """Mimics requests.HTTPError: carries a .response with .status_code/.text."""

    def __init__(self, status, text=""):
        super().__init__(f"{status} Client Error")
        self.response = type("R", (), {"status_code": status, "text": text})()


def test_post_backs_off_and_retries_on_429():
    payload = {"open": [1], "high": [1], "low": [1], "close": [1],
               "volume": [1], "timestamp": [1704067200]}
    sess = FakeSession([FakeHTTPError(429, '{"805":"Too many requests"}'), FakeResp(payload)])
    client = DhanDataClient("JWT", "C1", session=sess, sleep=lambda _s: None)
    bars = client.historical_daily("1", "NSE_EQ", "2024-01-01", "2024-01-02")
    assert len(bars) == 1
    assert len(sess.calls) == 2  # 429 (Dhan 805) backed off and retried


def test_post_does_not_retry_other_4xx():
    sess = FakeSession([FakeHTTPError(400, "bad request"), FakeHTTPError(400, "bad request")])
    client = DhanDataClient("JWT", "C1", session=sess, sleep=lambda _s: None)
    with pytest.raises(Exception):
        client.historical_daily("1", "NSE_EQ", "2024-01-01", "2024-01-02")
    assert len(sess.calls) == 1  # a 400 is not retried
