# 06 — Build Phases

Build in this order. The strategy is a **lean vertical slice first**: get ONE strategy working end-to-end (fetch → store → scan → 100-day tracker → view) so real signals appear fast, then broaden to the other strategies and the full edge metrics. **After each phase, run the four review lenses** (see bottom) before moving on — issues are caught before the next layer is built on top, not at the end. Each phase has a clear "done" gate.

---

## Phase 0 — Foundations & guardrails (½ day)
- Create one **private** repo `the-swing-trades` with `worker/` (Python) and `web/` (Next.js) folders.
- Add `.gitignore` (env files, data, cache, `__pycache__`). Add secret-scan to CI.
- Set up GitHub Secrets (Dhan creds, Neon URLs) and Vercel env vars (point Vercel's Root Directory at `web/`).
- Provision Neon (free) + create the database.
- **Gate:** secrets resolve from env; nothing sensitive is committed.

## Phase 1 — Worker scaffold, DB schema, indicators (2–3 days)
- Package scaffold (`pyproject.toml`, editable install), config loader, `strategies.yaml`.
- Postgres schema + idempotent auto-init; `trading_calendar` with NSE holidays.
- Indicators (RSI, ATR, Supertrend, 14-day vol avg) via **`pandas-ta`** (not TA-Lib) + candle patterns.
- Logging (structured, rotation enforced + tested), IST time utils.
- **Unit tests** on indicators, candle patterns, time utils, schema init.
- **Gate:** all unit tests pass; schema applies cleanly to a fresh Neon DB.

## Phase 2 — Dhan data layer (2–3 days)
- TOTP token generation (PIN + TOTP secret → 24h token).
- Instrument-master loader (universe → `instruments`, dual-listing by ISIN).
- Historical backfill (per-security) → `price_history`.
- Daily bulk-quote fetcher (`/marketfeed/quote`, batched, retries/backoff).
- **Gate:** a real run authenticates, loads the universe, backfills history, and fetches a day of OHLCV incl. volume into Neon.

## Phase 3 — Scan pipeline & tracker, ONE strategy end-to-end (2–3 days)
- `run_scan.py`: trading-day check → fetch → freshness gate → store → indicators → strategies → `scan_signals` (append-only) → tracker update (configurable-horizon windows, capturing `entry_close` + `entry_next_open`) → `scan_runs`.
- Ship the **first strategy only** (`bullish_vol_rsi_candle`) so the whole pipeline is proven before adding more.
- **Edge metrics (first cut):** compute and store `strategy_metrics` (hit rate **vs base rate vs index**, expectancy, win/loss, sample size) against both entry references.
- Watchdog: always emit a success/failure artifact + alert (Telegram/email).
- **Integration test: assert ≥1 row written after a mocked scan** (the v1 0-byte-DB fix) — runs in CI.
- **Gate:** a full scan against mocked Dhan responses writes signals + tracker rows for the one strategy; re-running the same date does not double-insert; metrics show hit rate alongside base rate + index.

## Phase 4 — GitHub Actions cron (½–1 day)
- Workflow: scheduled (~14:00 UTC), runs the scan, uploads the health artifact.
- Catchup logic (`run_scan_if_needed`) for missed days.
- **Gate:** the scheduled workflow runs end-to-end on GitHub's runners, writes to Neon, and the artifact appears.

## Phase 5 — Dashboard (Next.js) (3–5 days)
- Next.js App Router + Tailwind + shadcn/ui; dark navy theme.
- Read-only data layer (pooled Neon connection) behind **ISR** caching.
- KPI cards, the per-strategy efficiency band, the tracker tables, strategy selector, completed-stocks toggle, the 100-day performance view — start by showing the one strategy from Phase 3.
- **Mobile-first responsive:** tables → stacked cards below a breakpoint; charts resize; tested on real iOS Safari + Android Chrome.
- "What am I looking at" explainer panel + "research tool, not financial advice" disclaimer + "last successful scan" badge + never-blank seed state.
- **Gate:** loads instantly on phone and laptop; no layout breakage; never renders empty.

## Phase 5.5 — Broaden the slice
- Add the remaining strategies (`top_breakout`, `supertrend_buy`) now that the pipeline + dashboard are proven.
- Fill out the full edge-measurement view (all horizons, hit rate at +5%/+10%, distribution) across strategies.
- **Gate:** all three strategies produce signals + tracker entries + metrics; the dashboard's strategy selector switches between them.

## Phase 6 — Polish, PWA, deploy (1–2 days)
- PWA manifest + icons (installable on phone/desktop).
- Final pass on the README (personal reference) + architecture diagram.
- **Gate:** live on Vercel, installable as a PWA, README complete.

---

## Phase 7 — Historical backtest (DEFERRED to v2.1, not in first launch)
- Replay past years using `price_history`, applying the same strategies, entry-realism, and benchmarking.
- **Must use a point-in-time universe** (include then-listed, now-delisted stocks) to avoid survivorship bias.
- Purpose: get an edge estimate in days instead of waiting ~5 months for forward-tracked cohorts.
- Not built in v2.0; the schema is already designed to support it (see 03_DATA_MODEL "Backtest readiness").

---

## Per-phase review lenses (run after every phase)
1. **Improvement / refactor** — maintainability, structure, performance, dead code.
2. **Bug & edge-case hunter** — timezones, empty data, connection limits, idempotency, data correctness, splits.
3. **Operability / "non-technical builder"** — secrets exposure, config drift across local/Actions/Vercel, deployment pitfalls, failure visibility.
4. **Feasibility / simplification** — anything overbuilt; simpler libraries or patterns.

## Definition of done (before calling it live)
- [ ] Integration test asserting DB rows are written — green in CI.
- [ ] Log-rotation test asserting old logs are purged.
- [ ] A real scheduled scan has run on GitHub Actions and written to Neon.
- [ ] Dashboard verified on a real phone and a laptop — no broken layout, instant load.
- [ ] The repo is private; no secret anywhere in tracked files.
- [ ] App never renders empty; "last successful scan" badge shows a real date.
