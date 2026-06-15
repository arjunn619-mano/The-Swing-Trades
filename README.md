# The Swing Trades

A **personal** end-of-day NSE/BSE stock screener with a 100-trading-day swing tracker. It screens the full equity universe each evening via the Dhan API, tracks every qualifying stock for 100 trading days, and measures whether each strategy actually has edge (hit rate benchmarked against the market).

**Research and observation tool — not a trading or order-routing system. It never places orders. Nothing here is financial advice.**

## Status
🚧 **Building.** Planning is complete; the worker is being scaffolded.

## Repo layout
- `worker/` — Python scan (runs on GitHub Actions cron, writes to Neon Postgres)
- `web/` — Next.js + Tailwind + shadcn/ui dashboard (deployed on Vercel, read-only)
- `Planning Pack/` — the full blueprints (start at `Planning Pack/00_INDEX.md`)
- `Planning Pack/09_README.md` — the detailed project README

## How it works (one line)
`Dhan API → GitHub Actions (nightly scan, Python) → Neon Postgres → Next.js dashboard (Vercel)`

See `CLAUDE.md` for the build conventions and the 8 architectural rules.
