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

-- Dashboard "starred" / favourite stocks. Written by the web app's /api/star route
-- (the web app also CREATEs this IF NOT EXISTS, so it works without re-running init_db).
CREATE TABLE IF NOT EXISTS starred (
    instrument_id  BIGINT PRIMARY KEY REFERENCES instruments(id) ON DELETE CASCADE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_price_history_date ON price_history (trade_date);
CREATE INDEX IF NOT EXISTS idx_scan_signals_run ON scan_signals (scan_run_id);
CREATE INDEX IF NOT EXISTS idx_scan_signals_strategy_date ON scan_signals (strategy_id, trade_date);
CREATE INDEX IF NOT EXISTS idx_tracker_obs_entry ON tracker_observations (tracker_entry_id);
CREATE INDEX IF NOT EXISTS idx_tracker_entries_status ON tracker_entries (status);

-- === Options module (Planning Pack/11_OPTIONS_MODULE.md) ===
-- Catalog of every index/stock option contract from the instrument master.
CREATE TABLE IF NOT EXISTS option_contracts (
    id                     BIGSERIAL PRIMARY KEY,
    security_id            TEXT UNIQUE NOT NULL,
    underlying_symbol      TEXT NOT NULL,                 -- e.g. RELIANCE, NIFTY
    underlying_security_id TEXT,
    exchange               TEXT NOT NULL,                 -- NSE | BSE
    instrument_type        TEXT NOT NULL,                 -- OPTIDX | OPTSTK
    expiry_date            DATE NOT NULL,
    strike                 NUMERIC(18,4) NOT NULL,
    option_type            TEXT NOT NULL,                 -- CE | PE
    lot_size               INTEGER,
    display_name           TEXT,
    active                 BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One tracked contract; enrolled the first day its volume > 1L (Planning Pack 11). Entry
-- premium permanent (mirrors Rule 3). Deleted on expiry — full history lives in the Parquet archive.
CREATE TABLE IF NOT EXISTS option_tracker (
    id              BIGSERIAL PRIMARY KEY,
    contract_id     BIGINT UNIQUE NOT NULL REFERENCES option_contracts(id) ON DELETE CASCADE,
    first_seen_date DATE NOT NULL,
    entry_ltp       NUMERIC(18,4) NOT NULL,               -- permanent
    entry_iv        NUMERIC(12,4),
    entry_oi        BIGINT,
    expiry_date     DATE NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',       -- active | expired
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Append-only per-day curve for a tracked contract. Tracked independently (no underlying
-- price); return_vs_entry is the option's own premium return from the add-date.
CREATE TABLE IF NOT EXISTS option_observations (
    id              BIGSERIAL PRIMARY KEY,
    tracker_id      BIGINT NOT NULL REFERENCES option_tracker(id) ON DELETE CASCADE,
    trade_date      DATE NOT NULL,
    ltp             NUMERIC(18,4),
    open            NUMERIC(18,4),
    high            NUMERIC(18,4),
    low             NUMERIC(18,4),
    close           NUMERIC(18,4),
    volume          BIGINT,
    oi              BIGINT,
    oi_change_pct   NUMERIC(12,4),
    iv              NUMERIC(12,4),
    delta           NUMERIC(12,6),
    theta           NUMERIC(12,6),
    gamma           NUMERIC(12,6),
    vega            NUMERIC(12,6),
    days_to_expiry  INTEGER,
    return_vs_entry NUMERIC(12,6),
    UNIQUE (tracker_id, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_option_contracts_underlying ON option_contracts (underlying_symbol);
CREATE INDEX IF NOT EXISTS idx_option_contracts_expiry ON option_contracts (expiry_date);
CREATE INDEX IF NOT EXISTS idx_option_tracker_status ON option_tracker (status);
CREATE INDEX IF NOT EXISTS idx_option_observations_tracker ON option_observations (tracker_id);

-- === News-driven "positive news" strategy (news_positive) ===
-- One frozen 10-value catalyst enum, tagged on both the audit trail (scan_signals) and the
-- tracker entry so hit-rate can later be sliced BY catalyst type. Nullable everywhere: the
-- systematic strategies (rsi/ema/etc.) leave these NULL; only news_positive rows carry them.
-- Added via ADD COLUMN IF NOT EXISTS so re-running init_db is a no-op (v1 idempotency lesson).
ALTER TABLE tracker_entries
    ADD COLUMN IF NOT EXISTS catalyst_tag       TEXT,   -- one of the 10 enum values (see CHECK below)
    ADD COLUMN IF NOT EXISTS catalyst_source    TEXT,   -- BSE | NSE | RSS_GNEWS | RSS_ET | RSS_LIVEMINT | RSS_PRWIRE | RSS_MC
    ADD COLUMN IF NOT EXISTS catalyst_decision  TEXT,   -- DETERMINISTIC | SEMI_LLM | LLM_ONLY
    ADD COLUMN IF NOT EXISTS catalyst_event_raw TEXT,   -- verbatim BSE CATEGORYNAME|SUBCATNAME or NSE subject
    ADD COLUMN IF NOT EXISTS catalyst_headline  TEXT,
    ADD COLUMN IF NOT EXISTS catalyst_url       TEXT,   -- NSURL / PDF / attchmntFile
    ADD COLUMN IF NOT EXISTS llm_event_type     TEXT,   -- Gemini/Haiku event_type (nullable for deterministic rows)
    ADD COLUMN IF NOT EXISTS llm_sentiment      TEXT;   -- positive | neutral | negative (nullable for deterministic rows)

ALTER TABLE scan_signals
    ADD COLUMN IF NOT EXISTS catalyst_tag       TEXT,
    ADD COLUMN IF NOT EXISTS catalyst_source    TEXT,
    ADD COLUMN IF NOT EXISTS catalyst_decision  TEXT,   -- audit incl. dedup decision (NEW_ENROLMENT | APPEARANCE_INCREMENT | MERGED)
    ADD COLUMN IF NOT EXISTS catalyst_event_raw TEXT,
    ADD COLUMN IF NOT EXISTS catalyst_headline  TEXT,
    ADD COLUMN IF NOT EXISTS catalyst_url       TEXT,
    ADD COLUMN IF NOT EXISTS llm_event_type     TEXT,
    ADD COLUMN IF NOT EXISTS llm_sentiment      TEXT;

-- The 10-value catalyst enum, enforced at the DB (adding a value later is a deliberate migration,
-- which keeps the sliced hit-rate history stable). ADD CONSTRAINT has no IF NOT EXISTS, so guard it.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'tracker_entries_catalyst_tag_chk') THEN
        ALTER TABLE tracker_entries ADD CONSTRAINT tracker_entries_catalyst_tag_chk
            CHECK (catalyst_tag IS NULL OR catalyst_tag IN (
                'RESULTS_POSITIVE','ORDER_WIN','ACQUISITION','BUYBACK','PARTNERSHIP',
                'NEW_PRODUCT','EXPANSION_CAPEX','RATING_UPGRADE','FUND_RAISING','OTHER_POSITIVE'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'scan_signals_catalyst_tag_chk') THEN
        ALTER TABLE scan_signals ADD CONSTRAINT scan_signals_catalyst_tag_chk
            CHECK (catalyst_tag IS NULL OR catalyst_tag IN (
                'RESULTS_POSITIVE','ORDER_WIN','ACQUISITION','BUYBACK','PARTNERSHIP',
                'NEW_PRODUCT','EXPANSION_CAPEX','RATING_UPGRADE','FUND_RAISING','OTHER_POSITIVE'));
    END IF;
END $$;

-- News-event ledger: the canonical (isin x catalyst_tag x day-window) event. Stage-B dedup upserts
-- here — an open event in-window MERGES onto its row (attach source, upgrade provenance) instead of
-- creating a duplicate tracker entry. `enrolled` flips true once the EOD scan prices the entry.
CREATE TABLE IF NOT EXISTS news_events (
    id               BIGSERIAL PRIMARY KEY,
    isin             TEXT NOT NULL,
    instrument_id    BIGINT REFERENCES instruments(id) ON DELETE SET NULL,
    catalyst_tag     TEXT NOT NULL,
    event_date       DATE NOT NULL,                              -- window start = first source timestamp
    window_end_date  DATE NOT NULL,                              -- event_date + NEWS_DEDUP_WINDOW_DAYS
    provenance       TEXT NOT NULL DEFAULT 'rss_unconfirmed',    -- rss_unconfirmed | exchange_confirmed
    headline         TEXT,
    url              TEXT,                                       -- link to glance at the news (NSURL/PDF/article)
    enrolled         BOOLEAN NOT NULL DEFAULT FALSE,             -- flipped once a tracker entry is priced
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE news_events ADD COLUMN IF NOT EXISTS url TEXT;  -- for DBs created before the url column
CREATE INDEX IF NOT EXISTS idx_news_events_lookup ON news_events (isin, catalyst_tag, event_date);
CREATE INDEX IF NOT EXISTS idx_news_events_unenrolled ON news_events (enrolled) WHERE enrolled = FALSE;

-- Permanent IPO / new-listing record. A mainboard stock (series EQ/BE/A/B) enters here the first
-- time it's seen with < 45 bars of history (a genuinely fresh listing — the backfilled starter
-- universe already has full history, and widened BSE X/XT/T are the wrong series). Once in, it
-- STAYS forever (unlike the rolling New-Listings view), so the page can show growth-since-listing
-- permanently. Populated idempotently by refresh_universe.
CREATE TABLE IF NOT EXISTS ipo_watch (
    instrument_id   BIGINT PRIMARY KEY REFERENCES instruments(id) ON DELETE CASCADE,
    first_seen_date DATE NOT NULL,             -- earliest stored bar when recorded ~= listing date
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Deterministic per-source idempotency: the same filing/headline re-ingested any number of times
-- collapses on UNIQUE(source_uid), so re-runs never double-count a source onto an event.
CREATE TABLE IF NOT EXISTS news_event_sources (
    id           BIGSERIAL PRIMARY KEY,
    event_id     BIGINT NOT NULL REFERENCES news_events(id) ON DELETE CASCADE,
    source_uid   TEXT UNIQUE NOT NULL,                           -- 'bse:'+NEWSID | 'nse:'+sha1 | 'rss:'+sha1
    source       TEXT NOT NULL,                                  -- BSE | NSE | RSS_GNEWS | ...
    url          TEXT,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_news_event_sources_event ON news_event_sources (event_id);

-- One-time (idempotent) catch-up for rows created before news_events.url existed: fill each event's
-- url from its earliest attached source, then propagate the LATEST event's url/headline onto the
-- matching news_positive tracker entry so already-enrolled picks become clickable. Guarded by IS NULL
-- so it only ever touches empties — a no-op on a fresh DB and on every subsequent run.
UPDATE news_events e SET url = s.url
FROM (SELECT DISTINCT ON (event_id) event_id, url FROM news_event_sources
      WHERE url IS NOT NULL ORDER BY event_id, id) s
WHERE s.event_id = e.id AND e.url IS NULL;

UPDATE tracker_entries te SET
    catalyst_url      = ev.url,
    catalyst_headline = COALESCE(te.catalyst_headline, ev.headline)
FROM (SELECT DISTINCT ON (instrument_id) instrument_id, headline, url
      FROM news_events WHERE instrument_id IS NOT NULL
      ORDER BY instrument_id, event_date DESC, id DESC) ev
WHERE te.instrument_id = ev.instrument_id
  AND te.strategy_id = (SELECT id FROM strategies WHERE key = 'news_positive')
  AND te.catalyst_url IS NULL AND ev.url IS NOT NULL;
