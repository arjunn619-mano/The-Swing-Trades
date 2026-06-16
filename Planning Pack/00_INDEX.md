# The Swing Trades — Planning Pack

**Status:** Planning complete, ready to build. **No application code is in this pack** — these are the blueprints the build follows.
**Last updated:** 15 Jun 2026 · Owner: Arjun

---

## What this is
A complete, reviewable specification for building **The Swing Trades** — a free, cloud-hosted, mobile-friendly **personal** research tool. It is the successor to an earlier locally-hosted NiceGUI tool. Read it line by line; the build kickoff prompt lives in `08_CLAUDE_CODE_BOOTSTRAP.md`.

## The project in one paragraph
A multi-strategy **end-of-day** NSE/BSE stock screener with a **100-trading-day** swing tracker. Once per evening after market close, an automated job pulls the full equity universe from the **Dhan API**, runs several independent screening strategies, and adds each qualifying stock to a persistent tracker. Every tracker entry is observed for 100 trading days from its first-seen date. Strategies are compared by **hit rate** (positive outcomes / total), benchmarked against the market, to discover which logic actually has edge. It is a **research and observation tool for personal use, not an order-routing system.**

## Reading order
| # | Document | What it covers |
|---|----------|----------------|
| 00 | **INDEX** (this file) | Overview, locked decisions, glossary |
| 01 | **ARCHITECTURE** | The 3-job split, tech stack, single-repo layout, system diagram |
| 02 | **PROCESS_FLOWS** | Step-by-step flows + diagrams (scan, auth, tracker, dashboard, deploy) |
| 03 | **DATA_MODEL** | Postgres schema, ER diagram, the 8 architecture rules mapped to tables |
| 04 | **DHAN_INTEGRATION** | Exact endpoints, TOTP auth, secrets, rate limits, universe loader |
| 05 | **STRATEGIES** | The 3 strategies, indicators, candle patterns, the strategy framework |
| 06 | **BUILD_PHASES** | Phased build plan (lean vertical slice first) with per-phase review gates and tests |
| 07 | **RISKS_AND_GUARDRAILS** | Build-time guardrails, v1 lessons, open items |
| 08 | **CLAUDE_CODE_BOOTSTRAP** | The build kickoff prompt |
| 09 | **README** | The project's README (personal reference) |
| 10 | **CRITICAL_REVIEW** | Pre-build critique + the adopted improvements (read this to see what changed and why) |
| 11 | **OPTIONS_MODULE** | Spec for the EOD stock-options tracker + Parquet archive (post-v1 addition) |

## Locked decisions (the spine)
- **Data source:** Dhan API — instrument master CSV (universe), Historical Data API (backfill), bulk Market Quote `/marketfeed/quote` (daily OHLCV incl. volume). No NSE scraping, no yfinance, no bhavcopy.
- **Auth:** Dhan 24h token, self-generated each run via **TOTP** (PIN + TOTP secret in GitHub Secrets). No manual login.
- **Worker (the scan):** **GitHub Actions** cron, in a **single PRIVATE repo** (holds the trading-capable secrets).
- **Database:** **Neon Postgres** (free), read through **Next.js ISR caching** so the dashboard hits the CDN, not the DB.
- **Frontend:** **Next.js + Tailwind + shadcn/ui** on **Vercel** (free Hobby), deployed from the `web/` folder of the same private repo. Installable as a **PWA** for phone + laptop access.
- **Repo layout:** one private monorepo — `worker/` (Python scan) + `web/` (Next.js dashboard).
- **Build order:** a **lean vertical slice first** — one strategy working end-to-end (fetch → store → scan → tracker → view) — then add the other strategies and the full edge metrics.
- **Out of scope:** order placement of any kind, live intraday price refresh, US/global tickers, the Agent OS layer, Excel export.

## Cost
**Zero new cost.** Vercel Hobby, Neon free, GitHub Actions free minutes (private repos get 2,000 free min/month — a daily ~5-min job uses a fraction), and the Dhan Data API (already paid ₹499/month by the user for other reasons → the project adds nothing).

## Glossary (terms used throughout)
- **EOD** — End of Day. The scan runs after market close; data is daily, not real-time.
- **Universe** — the full set of tradable NSE + BSE equities being screened (~2,000 stocks).
- **Signal** — a stock qualifying under a strategy on a given day.
- **Tracker entry** — a `(stock × strategy)` record observed for 100 trading days.
- **Hit rate** — share of tracker entries that achieved a positive outcome.
- **Trading day** — a day the exchange is open (weekends/holidays excluded).
- **ISR** — Incremental Static Regeneration: Next.js serves a cached page and refreshes it on a schedule, so the dashboard never waits on the database.
- **TOTP** — Time-based One-Time Password: the rotating 6-digit code mechanism; here the worker generates it itself from a stored secret.
- **PWA** — Progressive Web App: an installable web app with a home-screen icon and its own window.
