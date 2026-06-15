"""Environment-driven settings. No secret is ever hard-coded; values come from env
(local .env for dev, GitHub Actions Secrets in CI)."""
from __future__ import annotations

import os
from dataclasses import dataclass

try:  # optional for local dev; in CI the env is already populated
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional
    pass


@dataclass(frozen=True)
class Settings:
    # Neon Postgres
    database_url: str | None  # worker: direct (unpooled) read/write
    database_url_pooled: str | None  # web: pooled read

    # Dhan (worker only — these can place trades; keep private)
    dhan_client_id: str | None
    dhan_pin: str | None
    dhan_totp_secret: str | None

    # Failure alerts (worker watchdog)
    alert_telegram_bot_token: str | None
    alert_telegram_chat_id: str | None

    def require_database_url(self) -> str:
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is not set (Neon connection string).")
        return self.database_url

    def require_dhan(self) -> tuple[str, str, str]:
        missing = [
            name
            for name, val in (
                ("DHAN_CLIENT_ID", self.dhan_client_id),
                ("DHAN_PIN", self.dhan_pin),
                ("DHAN_TOTP_SECRET", self.dhan_totp_secret),
            )
            if not val
        ]
        if missing:
            raise RuntimeError(f"Missing Dhan secrets: {', '.join(missing)}")
        return self.dhan_client_id, self.dhan_pin, self.dhan_totp_secret  # type: ignore[return-value]


def load_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL"),
        database_url_pooled=os.getenv("DATABASE_URL_POOLED"),
        dhan_client_id=os.getenv("DHAN_CLIENT_ID"),
        dhan_pin=os.getenv("DHAN_PIN"),
        dhan_totp_secret=os.getenv("DHAN_TOTP_SECRET"),
        alert_telegram_bot_token=os.getenv("ALERT_TELEGRAM_BOT_TOKEN"),
        alert_telegram_chat_id=os.getenv("ALERT_TELEGRAM_CHAT_ID"),
    )
