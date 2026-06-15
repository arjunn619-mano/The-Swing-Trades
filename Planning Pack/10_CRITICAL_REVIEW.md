# 10 — Critical Review & Decisions

A pre-build critical pass over the whole plan (logic, methodology, tool stack, market positioning), grounded in industry/market research. Records what was found and what was adopted, so the reasoning is on the record.

*Reviewed: 09 Jun 2026.*

## What's strong (kept as-is)
The **reliability engineering** is the plan's best asset: idempotent writes, freshness gate, watchdog-always-emits-an-artifact, the CI test asserting rows were written, and the public/private repo split for credentials. The 3-job decoupling and "Vercel is only the UI" discipline are correct. None of the infra decisions (Dhan, TOTP, Neon, Vercel, GitHub Actions) were weakened.

## The core weakness found
The stated purpose is "compare strategies by hit rate to find edge," but **raw hit rate as originally defined cannot measure edge.** Three compounding issues:
1. **No base rate / benchmark** — in a rising market most stocks rise, so raw hit rate can look good while being worse than the universe or the index.
2. **Hit rate ≠ profitability** — 70% wins can still lose money if losers are large.
3. **Slow to learn** — forward-tracking alone takes ~5 months for a first cohort; the backtester (which gives fast edge estimates) had been cut.

## Decisions (all adopted; backtester deferred)
| # | Improvement | Decision | Where folded in |
|---|-------------|----------|-----------------|
| 1 | Benchmark hit rate vs **universe base rate + Nifty** (measure *excess*) | **Adopted** | 05 §1, 03 (tracker_observations, strategy_metrics), 06 Phase 3, 08, 09 |
| 2 | **Expectancy** + win/loss size + distribution | **Adopted** | 05 §2, 03 (strategy_metrics), 07 M2 |
| 3 | **Entry-price realism** — track `entry_close` AND `entry_next_open` | **Adopted** | 05 §3, 03 (tracker_entries), 07 M3, 08 |
| 4 | **Historical backtest** (point-in-time) | **Design-ready now, BUILD in v2.1** | 05 (deferred note), 03 (backtest readiness), 06 Phase 7 |
| 5 | **`pandas-ta` instead of TA-Lib** (CI install pain) | **Adopted** | 06 Phase 1, 08, 07 M8 |
| 6 | **Frame honestly** as edge-measurement; acknowledge the crowded landscape | **Adopted** | 09 (intro, highlights) |
| 7 | **Configurable horizon**, **param discipline**, **liquidity caveat** | **Adopted** | 05 §4–6, 07 M4/M5/M7 |

## Market reality (why honest framing matters)
The Indian EOD-screener space is crowded and commoditized — Chartink (free), Trendlyne, StockEdge (with backtesting), MarketInOut, and the broker's own **Dhan ScanX** ("50+ readymade screeners"). As a *product* this is not novel — but this is a personal tool, so novelty isn't the point. The value is the **measurement rigor + reliability engineering**: knowing whether these common signals actually have edge before acting on them. The README states this plainly.

## Honest framing of the strategies
RSI/volume/candle breakouts are common retail signals with marginal, regime-dependent edge at best. The project's value is **measuring** whether they work — against the right benchmark — not assuming they do. Small samples must never be read as edge. This is stated as a limitation in the README.

## Residual risks (unchanged, still true)
- Dependence on a single data source (Dhan); no price cross-check.
- Corporate-action (split/bonus) adjustment still deferred.
- Free-tier ceilings — comfortably clear, verify at build.

## Sources (research behind this review)
- Indian screener landscape: strike.money (Chartink/Screener alternatives), screener.in
- Backtesting biases (survivorship, look-ahead, data-snooping): QuantifiedStrategies, Auquan
- RSI/volume edge evidence: QuantifiedStrategies RSI backtest
- Survivorship bias in Indian small-caps: arXiv NIFTY Smallcap 250 study
