-- The Swing Trades — Postgres schema (Neon). Idempotent: safe to run on every startup.
-- Maps to Planning Pack/03_DATA_MODEL.md. The 8 architecture rules are enforced by the
-- UNIQUE constraints and the append-only / mutable split below.

-- Rule 4: one row per ISIN; NSE canonical, BSE scrip stored for reference.
CREATE TABLE IF NOT EXISTS instruments (
    id              BIGSERIAL PRIMARY KEY,
    isin            TEXT UNIQUE NOT NULL,
    security_id     TEXT NOT NULL,
    nse_symbol      TEXT,
    bse_scrip_code  TEXT,
    exchange_pref   TEXT NOT NULL DEFAULT 'NSE',
    segment         TEXT,
    symbol_name     TEXT,
    series          TEXT,
    lot_size        INTEGER,
    asm_gsm_flag    TEXT,
    active          BOOLEAN NOT NULL DEFAULT TRUE,   -- Rule M6: keep delisted as active=false
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS strategies (
    id            BIGSERIAL PRIMARY KEY,
    key           TEXT UNIQUE NOT NULL,
    display_name  TEXT NOT NULL,
    description   TEXT,
    active        BOOLEAN NOT NULL DEFAULT TRUE
);

-- Rule 6: the only mutable price table. Rule 4 (idempotency): unique (instrument, date).
CREATE TABLE IF NOT EXISTS price_history (
    id             BIGSERIAL PRIMARY KEY,
    instrument_id  BIGINT NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    trade_date     DATE NOT NULL,
    open           NUMERIC(18,4),
    high           NUMERIC(18,4),
    low            NUMERIC(18,4),
    close          NUMERIC(18,4),
    volume         BIGINT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (instrument_id, trade_date)
);

CREATE TABLE IF NOT EXISTS scan_runs (
    id              BIGSERIAL PRIMARY KEY,
    strategy_id     BIGINT REFERENCES strategies(id) ON DELETE CASCADE,
    trade_date      DATE NOT NULL,
    status          TEXT NOT NULL DEFAULT 'running',   -- running | success | failed
    qualified_count INTEGER NOT NULL DEFAULT 0,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    error           TEXT,
    UNIQUE (strategy_id, trade_date)
);

-- Rule 5: APPEND-ONLY audit trail. App code must never UPDATE or DELETE here.
CREATE TABLE IF NOT EXISTS scan_signals (
    id             BIGSERIAL PRIMARY KEY,
    scan_run_id    BIGINT NOT NULL REFERENCES scan_runs(id) ON DELETE CASCADE,
    instrument_id  BIGINT NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    strategy_id    BIGINT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    trade_date     DATE NOT NULL,
    close          NUMERIC(18,4),
    rsi            NUMERIC(10,4),
    volume_ratio   NUMERIC(10,4),
    candle_type    TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Rule 2: keyed on (instrument x strategy). Rule 3: entry_close permanent.
CREATE TABLE IF NOT EXISTS tracker_entries (
    id                    BIGSERIAL PRIMARY KEY,
    instrument_id         BIGINT NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    strategy_id           BIGINT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    first_seen_date       DATE NOT NULL,
    entry_close           NUMERIC(18,4) NOT NULL,     -- Rule 3: permanent, never updated
    entry_next_open       NUMERIC(18,4),              -- M3: realistic tradable entry
    appearance_count      INTEGER NOT NULL DEFAULT 1,
    last_seen_date        DATE NOT NULL,
    tracking_horizon_days INTEGER NOT NULL DEFAULT 100, -- Rule 8 / M5
    status                TEXT NOT NULL DEFAULT 'active', -- active | completed
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (instrument_id, strategy_id)
);

-- Per-day performance curve + benchmarks (M1) for each tracker entry.
CREATE TABLE IF NOT EXISTS tracker_observations (
    id                   BIGSERIAL PRIMARY KEY,
    tracker_entry_id     BIGINT NOT NULL REFERENCES tracker_entries(id) ON DELETE CASCADE,
    trade_date           DATE NOT NULL,
    trading_day_n        INTEGER NOT NULL,
    close                NUMERIC(18,4),
    return_vs_close      NUMERIC(12,6),
    return_vs_open       NUMERIC(12,6),
    universe_base_return NUMERIC(12,6),
    index_return         NUMERIC(12,6),
    UNIQUE (tracker_entry_id, trade_date)
);

-- Aggregated edge view (M1/M2): hit rate next to base rate + index, expectancy, etc.
CREATE TABLE IF NOT EXISTS strategy_metrics (
    id                BIGSERIAL PRIMARY KEY,
    strategy_id       BIGINT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    horizon_days      INTEGER NOT NULL,
    computed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    sample_size       INTEGER,
    hit_rate          NUMERIC(8,4),
    base_rate         NUMERIC(8,4),
    excess_hit_rate   NUMERIC(8,4),
    avg_win           NUMERIC(12,6),
    avg_loss          NUMERIC(12,6),
    expectancy        NUMERIC(12,6),
    median_return     NUMERIC(12,6),
    hit_rate_at_5pct  NUMERIC(8,4),
    hit_rate_at_10pct NUMERIC(8,4),
    avg_days_held     NUMERIC(8,2),
    UNIQUE (strategy_id, horizon_days)
);

-- Rule 7: static trading-day calendar.
CREATE TABLE IF NOT EXISTS trading_calendar (
    cal_date        DATE PRIMARY KEY,
    is_trading_day  BOOLEAN NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_price_history_date ON price_history (trade_date);
CREATE INDEX IF NOT EXISTS idx_scan_signals_run ON scan_signals (scan_run_id);
CREATE INDEX IF NOT EXISTS idx_scan_signals_strategy_date ON scan_signals (strategy_id, trade_date);
CREATE INDEX IF NOT EXISTS idx_tracker_obs_entry ON tracker_observations (tracker_entry_id);
CREATE INDEX IF NOT EXISTS idx_tracker_entries_status ON tracker_entries (status);
