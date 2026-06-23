import pytest

from swing_trades.data_layer import dhan_auth


class FakeResp:
    def __init__(self, payload, status=200):
        self._p = payload
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    def json(self):
        return self._p


def test_generate_token_sends_correct_params():
    captured = {}

    def fake_post(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return FakeResp({"accessToken": "JWT123", "expiryTime": "2026-06-16", "dhanClientId": "C1"})

    tok = dhan_auth.generate_access_token(
        "C1", "1234", "SECRET", http_post=fake_post, totp_code="654321"
    )
    assert tok.access_token == "JWT123"
    assert tok.expiry_time == "2026-06-16"
    assert captured["url"] == dhan_auth.AUTH_URL
    assert captured["params"] == {"dhanClientId": "C1", "pin": "1234", "totp": "654321"}


def test_generate_token_missing_token_raises():
    def fake_post(url, params=None, timeout=None):
        return FakeResp({"error": "bad pin"})

    with pytest.raises(RuntimeError):
        dhan_auth.generate_access_token(
            "C1", "1234", "S", http_post=fake_post, totp_code="000000", retries=0
        )


def test_generate_token_surfaces_dhan_message():
    # Dhan rejects the login with a 200 + {message,status}; the actual message must surface.
    def fake_post(url, params=None, timeout=None):
        return FakeResp({"status": "failed", "message": "Invalid TOTP"})

    with pytest.raises(RuntimeError, match="Invalid TOTP"):
        dhan_auth.generate_access_token(
            "C1", "1234", "S", http_post=fake_post, totp_code="000000", retries=0
        )


def test_generate_token_retries_with_fresh_code_then_succeeds():
    import pyotp

    calls = {"n": 0}

    def fake_post(url, params=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResp({"status": "failed", "message": "Invalid TOTP"})  # first try fails
        return FakeResp({"accessToken": "JWT-OK", "dhanClientId": "C1"})

    tok = dhan_auth.generate_access_token(
        "C1", "1234", pyotp.random_base32(), http_post=fake_post,
        totp_code="111111", sleep=lambda *_: None,  # no real wait in the test
    )
    assert tok.access_token == "JWT-OK"
    assert calls["n"] == 2  # retried once


def test_current_totp_is_six_digits():
    import pyotp

    code = dhan_auth.current_totp(pyotp.random_base32())
    assert len(code) == 6 and code.isdigit()
