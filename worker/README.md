# worker/ — The Swing Trades scan

Python 3.11+ end-of-day scan. Runs on GitHub Actions cron; writes to Neon Postgres. Never places orders.

**Planned package layout (Phase 1):**
```
worker/
  pyproject.toml            package metadata + deps (editable install)
  swing_trades/             the package
    config/                 settings + strategies.yaml loader
    core/                   indicators (RSI, ATR, Supertrend, vol-avg) + candle patterns
    db/                     Postgres schema + connection + idempotent auto-init
    data_layer/             Dhan auth (TOTP), universe loader, OHLCV fetcher, backfill
    strategies/             Strategy base + concrete strategies
    tracker/                100-trading-day lifecycle
    pipeline/               run_scan.py orchestration + watchdog
    metrics/                edge metrics (hit rate vs base rate + Nifty, expectancy)
    utils/                  logging (rotation), IST time/calendar
  scripts/                  init_db.py, run_scan.py, run_scan_if_needed.py, backfill.py
  tests/                    pytest (incl. the "rows written" integration test)
```
See `../Planning Pack/06_BUILD_PHASES.md`.
