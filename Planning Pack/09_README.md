# 09 — README (Personal Reference)

Draft of the README for the private `the-swing-trades` repo. This is a personal-use tool; the README is a note-to-self so future-me remembers what it is and how it works.

---

# The Swing Trades

A **personal framework for measuring whether end-of-day screening strategies actually have edge** on NSE/BSE. An automated daily job screens the full equity universe, then forward-tracks every qualifying stock and scores each strategy against the market, not just in isolation.

Plenty of tools *screen* stocks (Chartink, Trendlyne, StockEdge, the broker's own ScanX). This one exists to **honestly measure edge for my own use** — controlling for the market's base rate, win/loss size, and realistic entry — and to run unattended and reliably. That measurement rigor is the point.

**It is a research and observation tool — not a trading or order-routing system. Nothing here is financial advice.** It never places trades.

📱 Installable as a PWA on phone and desktop.

## What it does
- Pulls the full NSE + BSE equity universe (~2,000 stocks) once each evening via the Dhan API.
- Runs screening strategies (volume/RSI/candle breakouts and a Supertrend flip).
- Adds each qualifying stock to a persistent tracker keyed on `(stock × strategy)`.
- Observes every entry for a configurable window (default 100 trading days) and scores each strategy with **excess** hit rate (vs the universe base rate and the Nifty), **expectancy**, win/loss size, and sample size — and against **two** entry references (EOD close and realistic next-day open). A high raw hit rate in a rising market is not edge, and this makes that explicit.

## Architecture
Three decoupled jobs that meet only at the database:

```
Dhan API ──► GitHub Actions (nightly scan, Python) ──► Neon Postgres ──► Next.js dashboard (Vercel)
```

One private monorepo: `worker/` (Python scan) + `web/` (Next.js dashboard).

- **Worker** (`worker/`): Python on GitHub Actions cron. Generates its own Dhan token each run via TOTP, fetches the universe + daily OHLCV, computes indicators, runs strategies, updates the tracker. Always emits a health artifact.
- **Store:** Neon Postgres — append-only audit trail (`scan_signals`), mutable price history, and the tracker state.
- **Dashboard** (`web/`): Next.js + Tailwind + shadcn/ui on Vercel, read-only, served via ISR so it loads instantly and never hammers the database. Mobile-first and installable as a PWA.

## Engineering highlights
- **Reliability-first:** idempotent writes, a freshness gate, a CI integration test that asserts the scan actually wrote rows, and a watchdog that alerts on failure — designed against real bugs from v1 (a silent failure once left the database empty for a month).
- **Cost:** runs entirely on free tiers (Vercel Hobby, Neon, GitHub Actions).
- **Clean data layer:** official broker API instead of fragile web scraping; universe, history, and daily prices all from documented endpoints.
- **Honest metrics:** hit rate is always shown *next to* the market base rate and index return (so "edge" means excess, not raw), plus expectancy, win/loss size, and sample size. Forward-tracking is true out-of-sample (no look-ahead).

## Tech stack
Python · pandas · Dhan API · Neon Postgres · Next.js (App Router) · Tailwind · shadcn/ui · Vercel · GitHub Actions

## Strategies
| Strategy | Idea |
|----------|------|
| Bottom Breakout | Volume surge + low RSI + bullish candle |
| Top Breakout | Volume surge + high RSI (continuation) + bullish candle |
| Supertrend Buy | ATR-based trend flip from short to long with volume confirmation |

## Limitations (honest, for my own reference)
- Single data source (Dhan); no cross-validation of prices.
- Corporate-action (split/bonus) adjustment is not yet applied — rare events can distort an individual entry.
- Strategy edge is *measured*, not assumed — small samples should not be read as predictive.
- These are common retail signals with marginal, regime-dependent edge at best; the value is in measuring whether they work, not assuming they do.

## Disclaimer
For personal research and educational purposes only. Not investment advice. No buy/sell recommendation is implied.
