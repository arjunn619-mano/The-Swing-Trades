"""Unattended Dhan token generation via PIN + TOTP (Planning Pack/04_DHAN_INTEGRATION.md).

Dhan tokens last 24h; the worker mints a fresh one each run by computing the current TOTP
code from a stored secret and POSTing to the auth endpoint. No browser, no manual OTP.

We use a direct HTTP call (not the dhanhq SDK) deliberately: the worker is read-only and
needs only a few endpoints, the SDK's v2.2.0 is pre-release, and a thin call is trivially
mockable. `http_post` and `totp_code` are injectable so this is fully unit-tested offline.
"""
from __future__ import annotations

from typing import Callable, Optional

from .models import TokenInfo

AUTH_URL = "https://auth.dhan.co/app/generateAccessToken"


def current_totp(totp_secret: str) -> str:
    import pyotp  # lazy import

    return pyotp.TOTP(totp_secret).now()


def generate_access_token(
    client_id: str,
    pin: str,
    totp_secret: str,
    *,
    http_post: Optional[Callable] = None,
    totp_code: Optional[str] = None,
    timeout: int = 30,
) -> TokenInfo:
    if http_post is None:
        import requests  # lazy import

        http_post = requests.post

    code = totp_code or current_totp(totp_secret)
    resp = http_post(
        AUTH_URL,
        params={"dhanClientId": client_id, "pin": pin, "totp": code},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    token = data.get("accessToken") or data.get("access_token")
    if not token:
        raise RuntimeError(f"No accessToken in auth response: keys={list(data)}")
    return TokenInfo(
        access_token=token,
        expiry_time=data.get("expiryTime"),
        client_id=data.get("dhanClientId", client_id),
    )
