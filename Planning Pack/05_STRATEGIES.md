# 05 — Strategies

Three strategies ship in v2 (carried from v1). All parameters live in `config/strategies.yaml` so they can be tuned without code changes. Each strategy is evaluated independently and gets its own tracker entries and hit rate.

## Shared parameters (config/strategies.yaml)
| Param | Default | Meaning |
|-------|---------|---------|
| `volume_lookback_days` | 14 | Window for the average-volume baseline |
| `volume_ratio_min` | 1.5 | Today's volume must be ≥ this × the 14-day average |
| `volume_min_absolute` | 50000 | Hard floor on today's volume |
| `rsi_period` | 14 | RSI lookback |
| `rsi_min` / `rsi_max` | per strategy | RSI band |
| `require_candle_pattern` | true | Whether a bullish candle is required |
| `min_candle_score` | per strategy | Candle-pattern strength threshold |
| `prefer_exchange` | "NSE" | Dual-listing preference |

## The three strategies
| Key | Name | Logic |
|-----|------|-------|
| `bullish_vol_rsi_candle` | **Bottom Breakout** | Volume surge ≥ 1.5× 14-day avg **and** volume > 50K **and** RSI(14) < 50 **and** a bullish candle (Marubozu / Engulfing / Strong Green / Hammer / Long Lower Wick) |
| `top_breakout` | **Top Breakout** | Same volume + candle logic, but RSI(14) > 55 (continuation direction — opposite RSI side from Bottom Breakout) |
| `supertrend_buy` | **Supertrend Buy** | ATR(10), multiplier 3.0. Yesterday Supertrend was short; today it flips long; with volume confirmation |

## Indicators (definitions Claude Code must implement + unit-test)
- **RSI(14)** — Relative Strength Index over 14 periods.
- **ATR(10)** — Average True Range over 10 periods (for Supertrend).
- **Supertrend** — ATR(10), multiplier 3.0; tracks long/short flips day-over-day.
- **14-day average volume** — simple mean of the last 14 trading days' volume; `volume_ratio = today_volume / avg`.

## Candle patterns (bullish set)
Implement and unit-test each as a boolean over a single candle (or candle pair for engulfing):
- **Marubozu** (strong green, negligible wicks)
- **Bullish Engulfing** (today's green body engulfs yesterday's red body)
- **Strong Green** (large green body relative to range)
- **Hammer** (small body, long lower wick, little upper wick)
- **Long Lower Wick** (rejection of lows)
A `candle_type` and a `min_candle_score` let strategies require a minimum strength.

## Strategy framework (extensibility)
A strategy is a subclass of `Strategy` with:
- `key`, `display_name`, `description`
- `evaluate(ctx) -> Iterable[SignalRow]`
- Auto-registration via `__init_subclass__` (no manual registry edits).

**Adding a new strategy =** (1) create `strategies/<key>.py`, (2) add a YAML entry, (3) the startup auto-init registers it. No schema migration needed beyond the registry sync.

## How strategies are compared (the whole point) — edge measurement, not raw hit rate
**A raw hit rate cannot tell you whether a strategy has edge.** The measurement layer must control for the market, for win/loss size, and for realistic entry. This is the most important analytical part of the project.

### 1. Always benchmark hit rate against the base rate + the index
Raw "% of picks that went up" is meaningless alone — in a rising market most stocks rise anyway. For every strategy, over each entry's 100-trading-day window, also compute and display:
- **Base rate** — the % of the *entire universe* that rose over the same window (same start/end dates).
- **Index benchmark** — the Nifty 50 (or a broad index) return over the same window.
- **Excess hit rate / excess return** — the strategy's result *minus* the base rate / index. **Edge exists only if these are positive.**

### 2. Hit rate is not enough — measure expectancy and win/loss size
A strategy can be right 70% of the time and still lose money (small wins, large losers). Track and display, per strategy:
- Average return on winners vs average loss on losers; **expectancy** = (win% × avg win) − (loss% × avg loss).
- Median return and the return distribution; hit rate at +5% / +10%; average days held.

### 3. Entry-price realism (track two reference prices)
You cannot buy at a close you only observed at the close. So each tracker entry stores **both**:
- `entry_close` — EOD close on the first-seen date (the permanent reference, Rule #3).
- `entry_next_open` — the next trading day's open (the realistic, tradable entry).
Returns and all metrics above are computed against **both**, and reported separately. The realistic (next-open) figure is the honest one; the close figure is the idealized benchmark.

### 4. Configurable horizon
The 100-day window is a **config parameter** (`tracking_horizon_days`), not hardcoded. Report metrics across a few horizons (e.g., 20 / 60 / 100 / 250) so the choice is justified, not arbitrary.

### 5. Parameter discipline (avoid fooling yourself)
Strategy parameters (1.5× vol, 50K floor, RSI bands, ATR 10×3) are **fixed a priori** in `strategies.yaml` and must not be tuned to make results look good on the same data they're evaluated on (data-snooping / curve-fitting). Any future tuning uses a separate train/test split.

### 6. Liquidity caveat
The 50,000-share absolute volume floor admits genuinely illiquid stocks whose signals aren't realistically tradable and whose prices are easy to distort. This is acceptable for research but must be **stated as a limitation**; consider a higher floor or a turnover (price × volume) filter for an "actionable" view.

### Dashboard presentation
Per strategy: hit rate **next to** base rate and index (so excess is obvious), expectancy, sample size, and an efficiency band — so a lucky 5-name streak is never mistaken for edge.

## Historical backtest — DESIGN-READY NOW, BUILD IN v2.1 (deferred)
Forward-tracking is rigorous (true out-of-sample) but slow (~5 months to a first cohort). A **point-in-time historical backtest** replays past years to estimate edge in days. It is **not built in v2.0**, but the data model is designed so it can be added without rework. When built, it must use a **point-in-time universe** (include stocks that were listed *then*, even if delisted now) to avoid survivorship bias, and the same entry-realism and benchmarking rules above.

## Out of scope for v2 (explicitly)
- No order placement of any kind.
- No live intraday signals — EOD only.
- No US/global tickers.
- No second persistence layer.
