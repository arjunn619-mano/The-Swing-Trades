# The Swing Trades — Decision Draft (HISTORICAL LOG)

> **Superseded by the `Planning Pack/`.** This is the brainstorming log that led to the plan; kept for history. **15 Jun 2026 update:** finalized for **personal use** (recruiter framing dropped), renamed **The Swing Trades**, consolidated to a **single private repo** (`worker/` + `web/`), and sequenced as a **lean vertical slice first**. Wherever this log says "recruiter / public repo / portfolio", the Planning Pack overrides it.

**Status:** Historical brainstorming record. Last substantive update: **09 Jun 2026**.
**Rule for this doc:** everything is tagged **LOCKED** (decided), **LEANING** (probable, not final), or **OPEN** (needs research/decision).

---

## 0. Session checkpoint — 09 Jun 2026

**Where we are:** Architecture direction agreed in principle (3-job split: GitHub Actions worker → database → Vercel UI). Guardrails written. Not finalizing yet — user wants more research first.

**Decided (LOCKED):** Vercel-native rebuild (Next.js replaces NiceGUI) · public GitHub repo (account exists) · EOD-only, no live price refresh · skip Agent OS layer for v2 · responsive/multi-device from day 1 · all 8 v1 architecture rules carry over · 15 build-time guardrails (Section 9) baked in · review runs per-phase, not post-build (Section 10).

**Leaning (not final):** Neon Postgres + Next.js ISR cache (store) · **Dhan broker API** (data source — replaces Bhavcopy as primary) · GitHub Actions cron ~14:00 UTC / 7:30 PM IST · Next.js + Tailwind + shadcn/ui (UI).

**MAJOR UPDATE (09 Jun) — pivot to broker API.** Antigravity analysis + own verification of Dhan docs → pivot from scraping NSE Bhavcopy to the **Dhan API** (user already has access). Verdict:
- ✅ **Kills the Akamai/IP blocker** (our old #1 risk). Dhan needs static-IP whitelisting ONLY for order placement, NOT for data APIs → GitHub Actions' rotating IPs are fine for read-only data.
- ✅ **Unattended despite 24h token expiry:** set up **TOTP**, store Client ID + PIN + TOTP secret in GitHub Secrets, Action generates a fresh token each run. No daily manual login. (Doc's "30-day token" was wrong — tokens are 24h; TOTP is what makes it work.)
- ⚠️ **NOT free unconditionally:** Dhan **Data API** = free only if ≥25 trades/month, else **₹499+tax/month**. This is THE deciding fact vs alternatives. ← user to confirm.
- ⚠️ **Verify split/bonus adjustment:** confirm Dhan daily candles are adjusted; many broker feeds are raw/unadjusted. If raw → guardrail #3 still applies.
- Generous limits (daily candles: 365 days/request, 5 req/s, 100k/day) → whole ~2000-stock universe in minutes. No volume problem.

**Other antigravity suggestions — lead calls:** Keep **Neon (not Turso)** — fix cold-start with Next.js ISR/CDN caching (visitors hit edge cache, DB only written by daily cron), and Postgres is the more recognized skill. Keep **GitHub Actions (skip Modal)** — EOD timing slack is irrelevant; Modal credits ≠ free-forever. **Frontend locked:** Next.js + Tailwind + shadcn/ui.

**1 decision still to lock (was 2):**
- Data source cost path — see the open question below. (Data *store* is now settled as Neon + ISR.)

**OPEN — the one fact that locks the data source:** Does the user execute **≥25 trades/month on Dhan**? → If yes, Data API is free → **Dhan locked.** If no → it's ₹499/month; either accept that, or open a **free Upstox account** (Upstox historical/EOD API reportedly free with no trade requirement — verify), or fall back to Bhavcopy (Akamai risk).

**Research still to do:** (1) confirm Dhan daily candles split-adjusted; (2) Dhan instrument master → map universe to security_id; (3) confirm Upstox free historical API IF needed; (4) free-tier limits Neon/Vercel/GitHub; (5) portfolio embed (link/button vs iframe).

**STATUS 09 Jun (evening):** Data source locked = **Dhan** (user pays ₹499/mo already → zero new cost). TOTP set up & secret saved. ✅ **Planning pack generated** → see folder **`Planning Pack/`** (files 00–10): index, architecture, process flows, data model, Dhan integration, strategies, build phases, risks/guardrails, Claude Code bootstrap prompt, recruiter README. **Next action:** user reviews the pack line by line → then paste `08_CLAUDE_CODE_BOOTSTRAP.md` into Claude Code to start building. No app code until then.

---

---

## 1. Goal (unchanged from v1)
A personal **research/observation tool** for NSE/BSE swing-trade setups — NOT an order-routing system. One end-of-day scan after market close applies multiple screening strategies and tracks every qualifying stock for **100 trading days** from its first-seen date. Strategies are compared by **hit rate** to find which logic actually has edge.

## 2. New constraints for v2 (this is what changed)
- **Zero cost** — free tiers only, no credit card.
- **Opens on any device** — phone + laptop, just a link.
- **Recruiter-facing** — embedded/linked from personal portfolio site. Must look credible.
- **Public GitHub repo** — user already has a GitHub account. Repo doubles as portfolio + gives unlimited free Actions minutes.
- **Time-rich** — willing to do a proper rebuild, not a quick hack.

---

## 3. Core mental model — the app is THREE separate jobs
This resolves the "is it on Vercel or not?" confusion.

| Job | What it does | Where it runs in v2 | Can it run on Vercel? |
|---|---|---|---|
| **1. The worker** | Daily scan: download data, compute indicators, apply strategies | **GitHub Actions** (cron) | No (too long, no persistent process) |
| **2. The filing cabinet** | Store results permanently | **A database** (see OPEN) | No (Vercel storage is temporary) |
| **3. The screen** | Show results to anyone with the link | **Vercel** (Next.js) | **Yes — this is the only part on Vercel** |

v1 did all 3 jobs in one Python program on the PC. v2 splits them. Only **Job 3** is on Vercel.

---

## 4. Decisions so far

### LOCKED
- **No live price refresh** — EOD-only data. Simpler, fast on mobile, nothing to rate-limit. Recruiters won't miss it.
- **Skip the Agent OS layer** (MarketCIO / SignalAuditor / TruthGuard / Backtester) for v2. Ship the core screener first; add later if wanted.
- **Public GitHub repo** — free unlimited Actions + portfolio artifact.
- **Keep all 8 v1 architecture rules** (Section 7 below) — they are storage-agnostic and carry over intact.
- **Responsive / multi-device from day 1.** Layout must auto-adjust on phone + tablet + laptop with nothing broken. v1 (NiceGUI desktop tables) did NOT have this. Mobile-first design is a build requirement, not a later patch. (Details in Section 9.)

### LEANING (recommended, not final)
- **Frontend/UI:** **Next.js (React) on Vercel Hobby** — free, mobile-first, recruiter-credible. Replaces v1's NiceGUI (NiceGUI cannot run on Vercel).
- **Scheduler/worker:** **GitHub Actions cron**, runs ~7:30 PM IST (14:00 UTC), after bhavcopy is published. Replaces Windows Task Scheduler.
- **Database:** **Neon Postgres** (free tier) — shows real backend skill, supports growth. Alternative considered: static JSON committed to the repo (bulletproof but less impressive).
- **Data source:** **Dhan broker API** (primary, as of 09 Jun pivot — see Section 0). Reliable, no Akamai/IP block, TOTP-automated tokens. Bhavcopy demoted to fallback; yfinance to last resort. (Cost path pending — Section 0 open question.)

### Why Bhavcopy over yfinance (plain version)
- yfinance = phoning ~2,000 shops one at a time; slow, some don't answer, gets rate-limited from cloud IPs. This was v1's #1 failure (0-byte DB for a month).
- Bhavcopy = the exchange publishes ONE official file every evening with every stock's close. One download. Fast, complete, official, not rate-limited.
- Catch: a daily file has only that day's prices; indicators (RSI, ATR, vol avg) need history → accumulate daily files into the DB over time, with a one-time backfill at the start.

---

## 5. OPEN questions — research in the next 24h
1. **[TOP RISK] Can a GitHub Actions runner actually download the NSE bhavcopy?** NSE has anti-bot defenses (Akamai) and may block datacenter/non-India IPs.
   - **Root cause to remember:** the real risk is "request from a datacenter IP," not the specific site. So swapping the data source is a *correlated* fallback, not an independent one.
   - **Fallback chain (options, not locked):**
     1. Primary: GitHub Action downloads NSE/BSE **bhavcopy** (1 request).
     2. Fallback A: GitHub Action uses **yfinance**. May work (Yahoo is more tolerant of automation than NSE's site), but thousands of per-ticker calls from one shared IP risk rate-limiting; yfinance also breaks when Yahoo changes auth.
     3. **Graceful degradation:** if bhavcopy fails, use yfinance to update only **currently-tracked stocks** (few hundred, low rate-limit risk) → tracker windows stay honest, only new-signal *discovery* pauses that day.
     4. True IP fix: **PC** does a tiny daily fetch-and-push to Neon (residential India IP, like v1). Keeps zero-cost public app; only loses "PC can be off."
   - **Action item:** run a throwaway GitHub Action early to TEST whether bhavcopy and yfinance each work from a runner — do not assume. ~1 hour experiment.
2. **Exact bhavcopy source + format.** NSE moved to the new UDiFF bhavcopy format (mid-2024). Confirm the current download URL, file format, and whether headers/cookies are needed. Same for BSE bhavcopy.
3. **Universe list source.** Where to get the canonical NSE + BSE active equity list (with ISIN, symbol, BSE scrip code) for dual-listing resolution.
4. **India EOD data libraries** worth evaluating as bhavcopy wrappers/alternatives: `jugaad-data`, `nsepython`, `bhavcopy`, NSE official archives.
5. **Free-tier limits to confirm (current):** Neon (storage, autosuspend behavior), Vercel Hobby (build/bandwidth), GitHub Actions (minutes — moot if repo is public).
6. **Portfolio embed mechanism:** "Live Demo" button/link + screenshot card vs iframe. (Leaning: link/button, not iframe — cleaner on mobile.)
7. **Always-populated UX:** seeding/sample data + "last successful scan" badge so the app never renders empty on weekends/holidays/after a failed scan.

---

## 6. Strategies to carry into v2 (from v1, unchanged)
- **Bottom Breakout** (`bullish_vol_rsi_candle`): vol ≥ 1.5× 14d avg + vol > 50K + RSI(14) < 50 + bullish candle (Marubozu / Engulfing / Strong Green / Hammer / Long Lower Wick).
- **Top Breakout** (`top_breakout`): same vol + candle logic, RSI(14) > 55.
- **Supertrend Buy** (`supertrend_buy`): ATR(10), multiplier 3.0, short→long flip + volume confirmation.
- All parameter-driven via `config/strategies.yaml`.

## 7. The 8 architecture rules (carry over intact)
1. Scan and dashboard are decoupled. (In v2: enforced — scan is a GitHub Action, dashboard is a separate Vercel deploy.)
2. Tracker keyed on **(stock_id × strategy_id)**, not stock_id alone.
3. Entry price = EOD close on first-seen date, **permanent**. Reappearance only increments appearance_count.
4. **NSE preferred** when dual-listed by ISIN; BSE scrip code stored for reference.
5. `scan_signals` table is **append-only** (audit trail).
6. `price_snapshots` is the only mutable price table.
7. All times **IST (Asia/Kolkata)**; static NSE holiday list, reviewed annually.
8. Tracking window = **100 TRADING days**; reappearance does NOT extend it.

## 8. v1 lessons — do NOT repeat
- Don't put the project in OneDrive (87K+ cache files hammered sync). → local-only path.
- Log rotation must actually purge old files (v1 grew to 130 MB). → test it day 1.
- Scan writes failed silently inside a broad `except` (0-byte DB for a month). → **integration test asserting rows are written after a scan, in CI.**
- Worker must **always emit an artifact** (success summary OR loud failure alert) so a missing/empty result is itself a signal.
- git from day 1 (now covered — public repo).

---

## 8.5 Dhan data layer — CONFIRMED from local docs (09 Jun)
Read the local DhanHQ v2 docs + SDK + the course's Tradehull wrapper line by line. The entire data layer is covered by official Dhan endpoints that are **not** behind NSE's Akamai bot-wall (they're `api.dhan.co` + `images.dhan.co` CDN). Static IP is required ONLY for order placement (which we never do) → GitHub Actions' rotating IPs are fine.

**Three endpoints cover everything:**
1. **Instrument master CSV** — `https://images.dhan.co/api-data/api-scrip-master-detailed.csv` (one CDN file). Columns include `SECURITY_ID`, `ISIN`, `EXCH_ID` (NSE/BSE), `SEGMENT` (E=Equity), `SYMBOL_NAME`, `SERIES`, `ASM_GSM_FLAG`. → **Solves the universe loader AND the ISIN dual-listing rule (#4) AND BSE scrip reference in one file. No NSE scraping at all.**
2. **Historical Data** — `POST /v2/charts/historical` → daily OHLCV per security back to inception. Use for the **one-time backfill** + building indicator history (RSI/ATR/vol-avg/supertrend need trailing days). One call per stock; daily candles allow 365 days/request.
3. **Bulk Market Quote** — `POST /v2/marketfeed/quote` (or `/ohlc`) → **up to 1000 instruments per request**, 1 req/sec. → the whole ~2000-stock universe in **2–3 calls** for the daily OHLCV update. (Confirm `/quote` includes **volume**; `/ohlc` may be OHLC+LTP only — strategies need volume.)

**Daily scan design (clean + fast):** backfill once via Historical API → each evening pull the universe's OHLCV via bulk Market Quote (2–3 calls) → append to DB → compute indicators → run strategies. Few calls, official API, reliable.

**Unattended token — CONFIRMED:** Dhan tokens are **24h only** (SEBI rule — no months-long token exists). TOTP does NOT extend expiry; it lets the **code generate the 24h token itself** (compute the 6-digit code from a stored secret, call `generateAccessToken`) instead of a manual browser+OTP login. 24h is fine because the cron runs once daily and mints a fresh token at the start of each run. Official `dhanhq` SDK v2.2.0 supports this: `DhanLogin.generate_token(pin, totp)`.

**Auth security (refinement):** the stored PIN + TOTP secret generates a **full-access** token (can place trades — Dhan has no read-only data token). So treat those secrets as account-level credentials. **Decision: split repos** — worker/scan + secrets in a **PRIVATE** GitHub repo (private repos still get 2,000 free Action min/month; daily ~5-min job uses a fraction); only the **Next.js frontend is PUBLIC** as the portfolio piece. Trading-capable secrets never sit in a public repo.

**Lead call — SDK, not the course wrapper.** Use the official **`dhanhq` SDK** (maintained, clean). The course `Dhan_Tradehull_V2.py` (1879 lines, Python 3.8, full of order-placement/option-chain code) is a useful *reference* for response-parsing snippets, but do NOT take it as a dependency — it bloats the project and adds order-routing surface a read-only research tool must never have.

**Net effect:** Bhavcopy and yfinance are now fully dropped. The data layer — historically this project's #1 failure source — is entirely on official Dhan endpoints with no Akamai/IP risk. Old research items "bhavcopy URL/format", "universe list source", "jugaad-data/nsepython" → **closed/obsolete.**

**Still open (small):**
- (a) ✅ RESOLVED — `/marketfeed/quote` (full mode) returns `volume` (total traded volume for the day) + OHLC + avg price + LTP for up to 1000 instruments/call. Daily scan uses this endpoint → whole universe OHLCV in 2–3 calls.
- (b) Corporate-action (split/bonus) adjustment — local FAQ was client-rendered/empty; unconfirmed whether Dhan data is adjusted. **Deferred per user** (rare per-stock; averaged hit-rate absorbs noise). Later fix: detect big overnight gap → flag/skip, or pull corporate-action list and adjust.
- (c) Free-tier limits Neon/Vercel/GitHub — sanity check only; usage is far below all ceilings. Verify current numbers at build time.
- (d) ✅ Portfolio embed — DECIDED: "Live Demo" link/button + screenshot card (not iframe). Opens the real app full-screen; clean on mobile.

**Optional enhancement — "app on my device":** make the Next.js app an installable **PWA** (add manifest + icons). Same codebase + same free Vercel hosting → installable icon on phone AND desktop, opens in its own window like a native app. Note: still reads from the cloud DB (needs internet for fresh data). True native installer (`.exe` in a folder) possible via Tauri/Electron but unnecessary for a read-only dashboard. Local-run (clone + run on PC) available as a dev/"local mode".

## 9. Build-time requirements & guardrails (BAKE IN — do not patch later)
Philosophy: prevent at design time. Each row is a known risk + the thing the code must do from line one. These feed directly into the Claude Code pack as hard constraints (like the v1 "rules" and "lessons").

| # | Risk / issue | Baked-in requirement | Phase |
|---|---|---|---|
| 1 | **Multi-device layout breaks** (v1 was desktop-only) | Mobile-first. Dense tables → stacked cards below a breakpoint, or horizontal scroll w/ frozen first column. Charts resize. Tap-friendly targets. Test on real iOS Safari + Android Chrome. | UI |
| 2 | **DB password leaks via public repo** | Secrets only in GitHub Actions Secrets + Vercel env vars. `.env` git-ignored. Secret-scan before push. Never hardcode connection strings. | All |
| 3 | **Splits/bonuses silently corrupt signals** (entry price + RSI/indicators break) | Adjust historical prices for corporate actions (or use adjusted series). Store adjustment factor. Detect splits on ingest. | Scan |
| 4 | **Re-running a scan double-inserts** (catchup scan `run_scan_if_needed`) | Idempotent writes: unique constraints + upsert on (strategy_id, trade_date, stock). | Scan/DB |
| 5 | **Serverless "too many connections"** to Neon | Use Neon **pooled** connection string. No per-request unpooled connections. | DB/API |
| 6 | **Cron runs before bhavcopy ready → empty/stale data** | Freshness gate: verify file is today's + trading day before writing. Skip weekends/holidays. Retry w/ backoff. | Scan |
| 7 | **Timezone off-by-one** (cron=UTC, market=IST) | All logic in IST (Asia/Kolkata). Single trading-day calendar w/ static NSE holiday list. Cron documented as UTC→IST. | Scan |
| 8 | **Silent failure (v1 0-byte DB for a month)** | Worker ALWAYS emits an artifact (success summary OR alert). Failure notification (email/Telegram). CI integration test asserts ≥1 row written after a scan. | Scan/CI |
| 9 | **App renders blank** (holiday / failed scan / first load) | Seed/sample data so UI is never empty. "Last successful scan: <date>" badge. | UI |
| 10 | **Source schema drift** (NSE UDiFF change, yfinance auth change) | Validate expected columns on ingest; fail loudly, don't write garbage. | Scan |
| 11 | **Config drift across 3 environments** (local / Actions / Vercel) | Single documented map of "which secret/var lives where." One config source of truth. | All |
| 12 | **Free-tier autosuspend latency** (Neon sleeps → slow first load) | Daily cron keeps DB warm; UI shows loading states; expect cold start. | Infra |
| 13 | **Log bloat / no rotation** (v1 grew to 130 MB) | Enforce rotation w/ backupCount; test it. (Less critical in cloud, still applies to any local component.) | Scan |
| 14 | **Mobile perf on big tables** | Pagination / virtualization; lazy-load charts. | UI |
| 15 | **Recruiter can't tell what it is** | Plain-English explainer panel + "research tool, not financial advice" disclaimer. OG tags for link previews. | UI |

## 10. Review lenses — run DURING the build, per phase (not post-build)
After EACH phase, run focused review passes (Claude Code subagents) so issues are caught before the next layer is built on top:
- **Improvement / refactor** — maintainability, structure, performance, dead code.
- **Bug & edge-case hunter** — splits, timezones, empty data, connection limits, idempotency, data correctness.
- **Operability / "non-technical builder"** — secrets exposure, config drift, deployment pitfalls, failure visibility, maintenance burden.
- **Feasibility / market research** — easier libraries (e.g. `jugaad-data`, `nsepython`), cheaper/simpler alternatives, anything overbuilt.

A final full-codebase pass at the end is fine as a backstop, but the substance lives in Sections 9 + per-phase review above.

## 11. Next step (when ready to finalize)
Once OPEN items are resolved, produce the Claude Code planning pack: `ARCHITECTURE.md`, `DATA_MODEL.md` (Postgres schema), `CLAUDE_CODE_BOOTSTRAP.md` (v2 bootstrap prompt, embedding Section 9 guardrails), `BUILD_PHASES.md` (with per-phase review gates from Section 10), and a recruiter-facing `README.md`. **No app code is written here** — that happens in Claude Code.
