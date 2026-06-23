"""Unattended Dhan token generation via PIN + TOTP (Planning Pack/04_DHAN_INTEGRATION.md).

Dhan tokens last 24h; the worker mints a fresh one each run by computing the current TOTP
code from a stored secret and POSTing to the auth endpoint. No browser, no manual OTP.

We use a direct HTTP call (not the dhanhq SDK) deliberately: the worker is read-only and
needs only a few endpoints, the SDK's v2.2.0 is pre-release, and a thin call is trivially
mockable. `http_post` and `totp_code` are injectable so this is fully unit-tested offline.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from .models import TokenInfo

AUTH_URL = "https://auth.dhan.co/app/generateAccessToken"


def current_totp(totp_secret: str) -> str:
    import pyotp  # lazy import

    return pyotp.TOTP(totp_secret).now()


def _seconds_to_next_totp_window(period: int = 30) -> float:
    """Time until the TOTP code rolls over, so a retry uses a genuinely fresh code."""
    return period - (time.time() % period) + 1.0


def generate_access_token(
    client_id: str,
    pin: str,
    totp_secret: str,
    *,
    http_post: Optional[Callable] = None,
    totp_code: Optional[str] = None,
    timeout: int = 30,
    retries: int = 1,
    sleep: Callable[[float], None] = time.sleep,
) -> TokenInfo:
    """Mint a Dhan access token from PIN + TOTP.

    Dhan returns HTTP 200 with a {message, status} body (no token) when it rejects the
    login — most often a TOTP code that crossed the 30-second boundary between minting
    and use. On that, wait for the next TOTP window and retry once with a fresh code.
    The wait keeps retries GENTLE (a ~30s gap, never a rapid burst) so we don't trip
    Dhan's auth anti-abuse throttle. If every attempt fails, the actual Dhan message is
    surfaced in the error so the cause is visible in the logs.
    """
    if http_post is None:
        import requests  # lazy import

        http_post = requests.post

    last_status = last_message = None
    data: dict = {}
    attempts = retries + 1
    for attempt in range(attempts):
        # First attempt may use an injected code (deterministic tests); retries always
        # mint a fresh code after the TOTP window rolls over.
        if attempt == 0:
            code = totp_code or current_totp(totp_secret)
        else:
            sleep(_seconds_to_next_totp_window())
            code = current_totp(totp_secret)

        resp = http_post(
            AUTH_URL,
            params={"dhanClientId": client_id, "pin": pin, "totp": code},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("accessToken") or data.get("access_token")
        if token:
            return TokenInfo(
                access_token=token,
                expiry_time=data.get("expiryTime"),
                client_id=data.get("dhanClientId", client_id),
            )
        last_status = data.get("status")
        last_message = data.get("message")

    raise RuntimeError(
        f"Dhan login failed after {attempts} attempt(s) — no accessToken. "
        f"status={last_status!r} message={last_message!r} response_keys={list(data)}"
    )
