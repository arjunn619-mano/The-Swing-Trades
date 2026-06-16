# 11 — Options Module (Spec for review)

**Status:** Spec only — **no code yet.** Read line by line and redline before we build, exactly like the original pack. Owner: Arjun.

Extends the equity screener with an **end-of-day stock-options tracker + full daily archive.** Like the rest of the project, it is **research/observation only — it never places orders.**

---

## What it is
Every evening, capture each NSE **stock-option** contract's EOD metrics (premium, OI, volume, IV, Greeks). Any contract that **traded > 1 lakh volume that day auto-joins the tracker**, with its entry premium locked on the add-date, and is then followed — **return % from add-date, plus OI/IV/Greeks day by day — until it expires.** The liquid (tracked) set is live in the dashboard; the **full** per-strike snapshot is archived as Parquet for offline analysis. It is **observation-first**: the first 1–2 months are for watching the data and tuning, not trading.

## Scope (v1)
- **Stock options** (`OPTSTK`): the **211 F&O underlyings**, every strike (ATM/OTM/ITM), CE + PE, all active monthly expiries (~**120k contracts**).
- **Index options** (`OPTIDX`) — **included**: NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, SENSEX, BANKEX, etc. (~18k contracts). We include **all** index underlyings; the **volume > 1L filter self-selects** the liquid ones, so we never hand-pick.
- Note: index options have **weekly** expiries, so those contracts live **~days** (short tracked window), and they trade far more than stock options — so 1L enrolls many near-ATM index strikes (fine for observation; a higher index threshold is a tuning candidate).

## Locked decisions
| Decision | Value |
|---|---|
| **Entry trigger** | A contract joins the tracker the **first day its daily volume > 1,00,000 (1 lakh)**. **No other filter.** |
| **Once enrolled** | **Tracked to expiry**, even if volume/OI later fade — we want the full arc. **Entry premium is permanent** (mirrors equity Rule 3). |
| **Window** | add-date → contract **expiry** (stock monthlies ≈ one cycle; index weeklies ≈ days), *not* a fixed 100 days. |
| **On expiry** | **Deleted from Postgres** (dashboard shows active contracts only); the full history lives on in the Parquet archive. |
| **Dashboard (live, free)** | Only the **volume-qualified** contracts → Neon Postgres → new **"Options"** section. |
| **Archive (offline, free)** | The **full** per-strike snapshot (every contract, all metrics) → daily **Parquet** → **GitHub Releases** (private repo) → synced to a **laptop folder** for pandas. |
| **Charts** | Option rows link to the **underlying's** TradingView chart (individual strikes chart poorly). |
| **Cadence** | **EOD only**, run after market close (≥ 3:30 PM IST) so IV/Greeks are closing values. No live monitoring. |

## Data — what Dhan gives us
The **Option Chain API is the single source**: one call per `(underlying, expiry)` returns **every strike** (CE + PE) with **LTP, volume, OI, previous-OI (→ OI-change%), IV, and full Greeks (δ/θ/γ/vega)**, plus the underlying's LTP. From that we derive **ATM IV, PCR, days-to-expiry, lot size**.

| Metric | Source | Backfillable? |
|---|---|---|
| Premium (LTP/OHLC), volume, OI, OI-change% | Option chain (also historical API for price/OI) | Price/OI: **yes**; IV/Greeks: **no** |
| IV, Greeks (δ/θ/γ/vega) | Option chain (**live snapshot only**) | **No** → accumulate forward from add-date (fits the model) |
| ATM IV, PCR, days-to-expiry | Derived per (underlying, expiry) | n/a |

**Rate-limit math:** chain allows **1 request / 3 sec**. Stock: ~211 underlyings × ~3 expiries ≈ 633 calls. Index: ~6–10 underlyings × ~5–10 active (weekly+monthly) expiries ≈ ~80 calls. Total ≈ **~700 calls × 3 s ≈ ~35–40 min/day** in GitHub Actions — well within the 6-hour job limit and the 100k/day data cap. **Fetching is not the constraint; storage is** (see below).

## Daily flow (new worker step, after the equity scan)
1. **Trading-day check** (reuse the calendar) — skip weekends/holidays.
2. **Refresh option catalog** from the instrument master (`OPTSTK` rows → `option_contracts`).
3. **Fetch chains:** for each underlying × active expiry, call `/optionchain` (throttled 1/3 s) → every strike's LTP/volume/OI/IV/Greeks.
4. **Enroll:** any contract with **today's volume > 1L** not already tracked → create an `option_tracker` entry (entry premium + IV locked).
5. **Observe:** for every active tracked contract → append today's `option_observations` row (premium, OI, OI-chg%, volume, IV, Greeks, underlying close, days-to-expiry, **return_vs_entry**).
6. **Expire:** any contract past its expiry → **delete its tracker + observations from Postgres** (its full history is already in the Parquet archive).
7. **Archive:** write the **full** snapshot (all ~120k strikes, all metrics) to `options_YYYY-MM-DD.parquet` → upload as an asset on the rolling **`option-archive`** GitHub Release.
8. **Health artifact** + observation log: #enrolled today, #active, DB size, archive size.

## Data model (Postgres — liquid subset only)
- **`option_contracts`** — catalog: `id`, `security_id` (UNIQUE), `underlying_symbol`, `underlying_security_id`, `exchange`, `expiry_date`, `strike`, `option_type` (CE/PE), `lot_size`, `display_name`, `active`.
- **`option_tracker`** — one row per contract: `id`, `contract_id` (UNIQUE), `first_seen_date`, `entry_ltp` (**permanent**), `entry_iv`, `entry_oi`, `status` (active/expired), `expiry_date`.
- **`option_observations`** — **append-only**, one row per `(tracker, trade_date)`: `ltp`, `open/high/low/close`, `volume`, `oi`, `oi_change_pct`, `iv`, `delta`, `theta`, `gamma`, `vega`, `days_to_expiry`, `return_vs_entry`. **No underlying price** — contracts are tracked **independently**, by their own premium. **UNIQUE (tracker, trade_date)** for idempotent upserts.
- **`option_chain_daily`** (optional) — per `(underlying, expiry, trade_date)`: `atm_iv`, `pcr`, `total_ce_oi`, `total_pe_oi`.

Same guardrails as equity: idempotent writes, append-only observations, permanent entry, all-IST.

## Archive (offline — every strike, including dead ones)
- **One Parquet/day** holding every `OPTSTK` contract with all metrics (~2–4 MB compressed).
- Uploaded as an asset on a single rolling **`option-archive`** GitHub Release (private; permanent; ≤ 2 GB/file).
- **Laptop sync:** a one-line `gh release download option-archive -D "D:\…\OptionArchive"` pulls new files into your folder; analyze with `pd.read_parquet`.
- **Why files, not the DB:** 120k × daily = millions of rows → multiple GB in Postgres (over the free tier). Parquet compresses to ~hundreds of MB/year and is built for offline crunching. The cloud worker writes it; the laptop (which need not be on) just **pulls a copy**.

## Dashboard — new "Options" section
- **Browse by underlying** (pick a stock → its tracked contracts) **and** a **global sortable/filterable table** like the equity tracker.
- **Columns:** ★ · Underlying · Strike · CE/PE · Expiry · Days left · **Entry LTP** · **Current LTP** · **Return %** · OI · OI-chg% · Volume · IV · Δ/θ/γ/vega · Chart ↗ (→ underlying).
- **Filters:** underlying, CE/PE, expiry, return (All/Pos/Neg), status (active/expired); sort any column.
- **Growth** = current LTP / entry LTP − 1 (premium return from add-date) — same read as the equity Return column.
- **Responsive:** desktop table → mobile cards (reuse the pattern). Read-only, ISR-cached, "research tool, not advice."

## Storage & cost
| Output | Size | Where | Cost |
|---|---|---|---|
| Liquid tracked contracts (active only) | small — kept lean because expired contracts are deleted | Neon Postgres | **Free** |
| Full daily snapshot (stock + index, every strike) | ~138k rows/day → ~3–5 MB/day → ~1 GB/yr | GitHub Releases | **Free** |
| Laptop copy | a few hundred MB | your folder | **Free** |

## Observation phase (first 1–2 months — watch, don't act)
Instrument the worker to log **daily enroll count, total active contracts, DB size, archive size**. Then tune, data-driven:
- The **1L threshold** — confirm the **volume unit** (contracts vs shares: the NIFTY chain's crore-scale volumes imply *shares*) and reset the number for stock options, which trade far less than index options.
- Whether to **cap strikes per underlying** and whether **index options need a separate (higher) threshold** than stock options.

## Build phases (when approved)
- **O1** — schema + option-catalog loader (from the instrument master) + tests
- **O2** — Dhan option data layer (`/optionchain` + `/optionchain/expirylist` fetch + parsers) + tests
- **O3** — option scan pipeline (enroll > 1L, observe, expire, return %) + integration test
- **O4** — Parquet archive + GitHub Releases upload + laptop sync script + docs
- **O5** — dashboard "Options" section (responsive)
- **O6** — observation instrumentation, then tune the threshold

## Open items (decide at review / during observation)
- Exact **volume unit** (contracts vs shares) — confirmed on the first live snapshot.
- Final **threshold** value(s) after observation — likely a **higher bar for index options** (they trade far more than stock options, so 1L enrolls many near-ATM index strikes).
- Whether to keep a short **"recently expired"** view in the dashboard, or rely entirely on the Parquet archive once a contract expires.
