# CLAUDE.md — The Swing Trades

Operational guide for building this repo. The full blueprints live in `Planning Pack/` (read `Planning Pack/00_INDEX.md` first). This file is the short, always-true summary.

## What this is
A **personal** end-of-day NSE/BSE stock screener with a **100-trading-day** swing tracker. Once each trading evening, an automated job pulls the equity universe from the **Dhan API**, runs screening strategies, and tracks every qualifying stock for 100 trading days from its first-seen date. Strategies are compared by **hit rate**, benchmarked against the market, to find which logic has edge.

> **It is a research/observation tool. It NEVER places orders.** No order-routing code, ever — even though the Dhan token technically can trade. That is a hard line.

## Repo layout (single PRIVATE monorepo)
```
the-swing-trades/        (private GitHub repo)
  worker/                Python 3.11+ scan — GitHub Actions runs this
  web/                   Next.js dashboard — Vercel deploys this folder
  Planning Pack/         the blueprints (source of truth, 00–10)
  Decision_Draft.md      historical brainstorming log
  Antigravity docs/      historical external review
  dhan/                  Dhan reference (API docs tracked; course bundle gitignored)
```
The repo is **private** because the stored Dhan secrets can place trades. GitHub Actions runs `worker/`; Vercel's Root Directory is set to `web/`.

## Tech stack (locked)
- **Worker:** Python 3.11+, official `dhanhq` SDK, `pandas` + `pandas-ta` (NOT TA-Lib), `pytest`, `pyotp`.
- **Data:** Dhan API only — instrument master CSV (universe), `/v2/charts/historical` (backfill), `/v2/marketfeed/quote` (daily OHLCV incl. volume). NO scraping, NO yfinance, NO bhavcopy.
- **DB:** Neon Postgres (pooled connection from the web app).
- **Web:** Next.js App Router + Tailwind + shadcn/ui + ISR caching; dark navy theme; installable PWA.
- **CI/host:** GitHub Actions (cron + tests), Vercel (Hobby).

## The 8 hard architectural rules (non-negotiable)
1. Scan and dashboard are decoupled. Dashboard is read-only over Postgres.
2. Tracker is keyed on `(instrument_id × strategy_id)`, not stock alone.
3. Entry price = EOD close on first-seen date and is **permanent**. Reappearance only increments `appearance_count`.
4. NSE preferred when dual-listed by ISIN; BSE scrip code stored for reference.
5. `scan_signals` is **append-only** (audit trail). Never UPDATE/DELETE.
6. `price_history` is the mutable price table; `scan_signals` is immutable.
7. All times **IST (Asia/Kolkata)**; static NSE holiday list in a `trading_calendar`.
8. Tracking window = **100 trading days** from `first_seen_date`; reappearance does NOT extend it.

## Build-time guardrails (bake in from line one)
- Secrets only in GitHub Secrets / Vercel env; `.env` git-ignored; secret-scan in CI.
- **Idempotent writes:** unique constraints + upsert on `price_history(instrument,date)` and `tracker_entries(instrument,strategy)`.
- **Freshness gate** before writing; skip weekends/holidays; never write stale/garbage data.
- Worker **always emits a success/failure artifact + alert**.
- **CI integration test asserts ≥1 row written after a mocked scan** (the v1 "0-byte DB for a month" fix).
- Edge metrics: hit rate always shown vs **universe base rate + Nifty**; store `entry_close` AND `entry_next_open`.
- Mobile-first responsive UI; never render empty (seed + "last successful scan" badge).
- Neon **pooled** connection from web; ISR so the dashboard hits the CDN, not the DB.

## Build order — lean vertical slice first
Phase 0 foundations → 1 worker scaffold + schema + indicators + tests → 2 Dhan data layer → 3 scan pipeline + tracker + **ONE strategy** (`bullish_vol_rsi_candle`) end-to-end + integration test → 4 GitHub Actions cron → 5 Next.js dashboard → 5.5 add the other 2 strategies + full edge metrics → 6 PWA + deploy. Run the 4 review lenses after each phase (see `Planning Pack/06_BUILD_PHASES.md`).

## Out of scope (v2.0)
Order placement of any kind; live intraday refresh; US/global tickers; a second persistence layer; the Agent OS layer; Excel export. Historical backtest is deferred to v2.1 (design the DB backtest-ready: keep delisted instruments as `active=false`).

## Conventions
- Use the official `dhanhq` SDK, NOT the course `Dhan_Tradehull` wrapper (it's order-routing-heavy reference only).
- No absolute paths; env-driven config. Log rotation enforced + tested.
- Strategy = subclass of `Strategy` with `key/display_name/description/evaluate(ctx)`, auto-registered via `__init_subclass__`; params live in `worker/config/strategies.yaml`.
