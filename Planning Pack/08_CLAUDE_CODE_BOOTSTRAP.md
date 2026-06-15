# 08 — Claude Code Bootstrap Prompt

This is the prompt that kicks off the build in Claude Code. It points at this planning pack and sets the hard rules. The pack folder lives in the repo, so Claude Code can read it directly.

---

```
You are helping me build The Swing Trades — a personal trading-research project.
Read the planning pack in "Planning Pack/" (files 00–10) before writing any code.

WHAT IT IS
A multi-strategy END-OF-DAY NSE/BSE stock screener with a 100-TRADING-DAY swing tracker.
It is a RESEARCH AND OBSERVATION tool for my personal use, NOT an order-routing system.
It never places trades. Once each trading evening, an automated job pulls the equity universe
from the Dhan API, runs several screening strategies, and tracks every qualifying stock for
100 trading days from its first-seen date. Strategies are compared by hit rate (benchmarked
against the market) to find which logic has edge.

ARCHITECTURE (three decoupled jobs — see 01_ARCHITECTURE.md)
1. Worker (scan): Python, runs on GitHub Actions cron.
2. Store: Neon Postgres (free).
3. Dashboard: Next.js + Tailwind + shadcn/ui on Vercel. Read-only. Installable PWA.
Only the dashboard is on Vercel. The scan is never on Vercel.

REPO LAYOUT (one PRIVATE monorepo — it holds trading-capable Dhan secrets)
the-swing-trades/            (private GitHub repo)
  worker/                    Python scan (GitHub Actions runs this)
  web/                       Next.js dashboard (Vercel deploys this folder)
  Planning Pack/             these blueprints (source of truth)
The repo is PRIVATE because the stored PIN + TOTP secret can place trades. Vercel deploys
the web/ subdirectory; GitHub Actions runs worker/.

TECH STACK (use exactly this unless I say otherwise)
- Worker: Python 3.11+, official `dhanhq` SDK, pandas + `pandas-ta` for indicators (NOT TA-Lib — it's painful to install on GitHub runners), pytest.
- Data: Dhan API only — instrument master CSV (universe), /v2/charts/historical (backfill),
  /v2/marketfeed/quote (daily OHLCV incl. volume). NO scraping, NO yfinance, NO bhavcopy.
- Auth: Dhan 24h token generated each run via PIN + TOTP (pyotp). Secrets in GitHub Secrets.
- DB: Neon Postgres, pooled connection from the web app.
- Frontend: Next.js App Router, Tailwind, shadcn/ui, ISR caching, dark navy theme.

HARD ARCHITECTURAL RULES (non-negotiable — call out any violation)
1. Scan and dashboard are decoupled. Dashboard is read-only over Postgres.
2. Tracker is keyed on (instrument_id × strategy_id), not stock alone.
3. Entry price = EOD close on first-seen date and is PERMANENT. Reappearance only increments appearance_count.
4. NSE preferred when dual-listed by ISIN; BSE scrip code stored for reference.
5. scan_signals is APPEND-ONLY (audit trail). Never UPDATE/DELETE.
6. price_history is the mutable price table; scan_signals is immutable.
7. All times IST (Asia/Kolkata); static NSE holiday list in a trading_calendar.
8. Tracking window = 100 TRADING days from first_seen_date; reappearance does NOT extend it.

BUILD-TIME GUARDRAILS (see 07_RISKS_AND_GUARDRAILS.md — implement from the start)
- Secrets only in GitHub Secrets / Vercel env; .env git-ignored; the repo is private.
- Idempotent writes: unique constraints on price_history(instrument,date) and tracker_entries(instrument,strategy).
- Freshness gate before writing; skip weekends/holidays.
- Worker ALWAYS emits a success/failure artifact + alert.
- CI integration test asserts >=1 row written after a mocked scan (the v1 0-byte-DB fix).
- Mobile-first responsive UI; tables become cards on small screens; test on real iOS Safari + Android Chrome.
- App must NEVER render empty; show a "last successful scan" badge; seed sample data.
- Neon pooled connection from the web app; ISR so the dashboard hits the CDN, not the DB.

STRATEGIES TO SHIP (parameter-driven via config/strategies.yaml — see 05_STRATEGIES.md)
- bullish_vol_rsi_candle (Bottom Breakout): vol >= 1.5x 14d avg + vol > 50K + RSI(14) < 50 + bullish candle.
- top_breakout (Top Breakout): same vol + candle logic, RSI(14) > 55.
- supertrend_buy: ATR(10), mult 3.0, short->long flip + volume confirmation.
Strategy framework: subclass Strategy with key/display_name/description/evaluate(ctx); auto-register via __init_subclass__.
Build the FIRST strategy (bullish_vol_rsi_candle) end-to-end first; add the other two once the slice works.

EDGE-MEASUREMENT LAYER (critical — see 05_STRATEGIES.md; raw hit rate is NOT enough)
- Every strategy's hit rate must be shown next to the UNIVERSE BASE RATE and the NIFTY return over the same window; edge = excess over those.
- Track expectancy (win% x avg win - loss% x avg loss), avg win/loss, median, hit rate at +5%/+10%, sample size.
- Each tracker entry stores TWO entry references: entry_close (EOD close, permanent) AND entry_next_open (realistic tradable entry); compute metrics against both.
- tracking_horizon_days is configurable (default 100); report across a few horizons.
- Fix strategy params a priori (no tuning on eval data). Document the low-volume liquidity caveat.
- Design the DB backtest-ready (keep delisted instruments as active=false for a point-in-time universe) but DO NOT build the backtest engine in v2.0 — it's a deferred v2.1 phase.

OUT OF SCOPE
Order placement of any kind; live intraday refresh; US/global tickers; a second persistence layer;
the Agent OS layer; Excel export.

BUILD ORDER — LEAN VERTICAL SLICE FIRST (see 06_BUILD_PHASES.md) — run the 4 review lenses after EACH phase:
Phase 0 foundations/secrets → 1 worker scaffold + schema + indicators + tests →
2 Dhan data layer → 3 scan pipeline + tracker + ONE strategy end-to-end + integration test →
4 GitHub Actions cron → 5 Next.js dashboard (responsive) showing that one strategy →
THEN broaden: add the other 2 strategies + full edge metrics → 6 PWA + deploy.

BEFORE WRITING ANY CODE:
Restate the goal and the 8 architectural rules back to me to confirm you have them right.
Then propose the monorepo file structure and the Phase 1 plan. Wait for my approval before scaffolding.
```

---

## Notes for the human (you)
- The pack folder lives in the repo root so Claude Code can read it directly.
- Don't paste any secret into Claude Code chat — secrets go into GitHub/Vercel settings only.
- Build the **worker** side first (Phases 0–4), confirm a real scan writes to Neon, *then* build the **web** dashboard (Phase 5) on top of real data.
- Get **one strategy working end-to-end** before adding the rest — see real signals fast, then broaden.
- Keep this pack updated if a decision changes mid-build; it's the source of truth.
