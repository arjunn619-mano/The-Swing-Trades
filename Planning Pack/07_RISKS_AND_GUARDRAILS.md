# 07 — Risks & Guardrails

## Build-time guardrails (bake in — do not patch later)
Each is a known risk + the thing the code must do from line one.

| # | Risk | Baked-in requirement | Phase |
|---|------|----------------------|-------|
| 1 | Multi-device layout breaks (v1 was desktop-only) | Mobile-first; dense tables → stacked cards below a breakpoint; charts resize; test on real iOS Safari + Android Chrome | 5 |
| 2 | DB password / Dhan creds leak via committed secrets | Secrets only in GitHub Secrets / Vercel env; `.env` git-ignored; secret-scan in CI; the repo is **private** and trading creds are never committed | 0 |
| 3 | Splits/bonuses corrupt signals | Deferred (rare). Later: detect big overnight gap → flag/skip, or adjust from corporate-action list | — |
| 4 | Re-running a scan double-inserts | Idempotent upserts; unique constraints on `price_history` and `tracker_entries` | 1/3 |
| 5 | Serverless "too many connections" to Neon | Use Neon **pooled** connection string from the web app | 5 |
| 6 | Cron runs before data is ready → empty/stale | Freshness gate verifies today's trading date before writing; skip weekends/holidays | 3 |
| 7 | Timezone off-by-one (cron UTC vs market IST) | All logic in IST; single `trading_calendar`; cron documented UTC→IST | 1 |
| 8 | Silent failure (v1: 0-byte DB for a month) | Worker always emits artifact; failure alert; CI integration test asserts rows written | 3 |
| 9 | App renders blank (holiday / failed scan / first load) | Seed/sample data; "last successful scan" badge; never-empty UI | 5 |
| 10 | Source schema drift (Dhan/CSV format change) | Validate expected columns on ingest; fail loudly, don't write garbage | 2 |
| 11 | Config drift across local / Actions / Vercel | One documented "which secret lives where" map (see 01_ARCHITECTURE) | 0 |
| 12 | Free-tier autosuspend latency (Neon sleeps) | ISR caching + daily cron keep it warm; loading states in UI | 5 |
| 13 | Log bloat / no rotation (v1 hit 130 MB) | Enforce rotation w/ backupCount; test it | 1 |
| 14 | Mobile perf on big tables | Pagination / virtualization; lazy-load charts | 5 |
| 15 | Forgetting at a glance what the tool is/does | Plain-English explainer panel + "research tool, not financial advice" disclaimer | 5 |

## v1 lessons — do NOT repeat
- **OneDrive killed performance** (87K+ cache files synced). → cloud now; no local cache hammering. N/A but noted.
- **Logs never purged** (130 MB / 26 files). → enforce + test rotation (Guardrail 13).
- **0-byte DB for a month** — scan writes failed silently in a broad `except`. → integration test in CI (Guardrail 8). **The single most important lesson.**
- **cmd window popped daily** (Task Scheduler). → N/A; cron is on GitHub now.
- **Hardcoded absolute paths broke on move.** → no absolute paths; env-driven config.
- **No git history.** → git from day one (one private repo).
- **Browser-scraper trackers failed silently.** → watchdog always emits an artifact (Guardrail 8).

## Open items (none block the build)
| Item | Status | Resolution |
|------|--------|------------|
| Bulk quote returns volume | ✅ Resolved | `/marketfeed/quote` returns `volume` |
| Corporate-action adjustment | Deferred | Rare; mitigation later (Guardrail 3) |
| Free-tier limits Neon/Vercel/GitHub | Sanity-check | Far below all ceilings; verify current numbers at build |
| PWA "app on device" | Optional | Add manifest + icons in Phase 6 |

## Methodology guardrails (added from the critical review — see 10_CRITICAL_REVIEW)
| # | Risk | Requirement |
|---|------|-------------|
| M1 | Raw hit rate mistaken for edge | Always show hit rate vs **universe base rate** + **index** over the same window; edge = excess |
| M2 | Hit rate hides losing strategies | Track **expectancy** + avg win/loss + distribution, not just % positive |
| M3 | Look-ahead in entry price | Store `entry_close` AND `entry_next_open`; report metrics against both |
| M4 | Curve-fitting / data snooping | Fix params a priori in YAML; no tuning on eval data |
| M5 | Arbitrary horizon | `tracking_horizon_days` configurable; report across horizons |
| M6 | Survivorship bias (in deferred backtest) | Point-in-time universe; keep delisted instruments (`active=false`) |
| M7 | Illiquid signals not tradable | Document the low-volume caveat; consider a turnover filter |
| M8 | TA-Lib CI install pain | Use `pandas-ta` (pure Python) |

## Residual risks worth watching (honest list)
- **Dhan data-API dependency.** If Dhan changes terms, raises data-API price, or has an outage, the scan can't run. Mitigation: watchdog alerts; the dashboard falls back to last-good data and shows the stale-date badge, never blank.
- **Token/secret compromise.** The stored PIN + TOTP secret can place trades. Mitigation: private repo, encrypted secrets, never logged; rotate if ever exposed.
- **Strategy edge is unproven.** This is a research tool — the point is to *measure* whether the strategies have edge, not to assume they do. Hit-rate with sample size keeps that honest; small samples must not be read as edge.
- **Single data source.** No cross-check on Dhan's numbers. Acceptable for a personal research tool; note it in the README's limitations.
