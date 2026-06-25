import { sql } from "./db";
import { num } from "./format";

export type Overview = {
  lastScanDate: string | null;
  lastScanStatus: string | null;
  activeCount: number;
  trackedCount: number;
  newListingCount: number;
};

export type Metric = {
  key: string;
  displayName: string;
  horizonDays: number;
  sampleSize: number;
  hitRate: number | null;
  baseRate: number | null;
  excessHitRate: number | null;
  expectancy: number | null;
  avgWin: number | null;
  avgLoss: number | null;
};

export type Signal = {
  symbol: string;
  name: string;
  exchange: string | null;
  strategy: string;
  close: number | null;
  rsi: number | null;
  volumeRatio: number | null;
  candleType: string | null;
  tradeDate: string;
};

export type TrackerRow = {
  instrumentId: number;
  symbol: string;
  name: string;
  exchange: string;
  strategy: string;
  firstSeenDate: string;
  entryClose: number | null;
  currentClose: number | null;
  appearanceCount: number;
  status: string;
  latestReturn: number | null;
  dayN: number | null;
};

export type NewListing = {
  instrumentId: number;
  symbol: string;
  name: string;
  exchange: string;
  bars: number;
  firstSeen: string;
  entryClose: number | null;
  currentClose: number | null;
  returnPct: number | null;
};

export type StarredRow = {
  instrumentId: number;
  symbol: string;
  name: string;
  exchange: string;
  lastClose: number | null;
};

export type OptionRow = {
  contractId: number;
  underlying: string;
  exchange: string;
  instrumentType: string; // OPTIDX | OPTSTK
  expiry: string;
  strike: number | null;
  optionType: string; // CE | PE
  lotSize: number | null;
  firstSeen: string;
  entryLtp: number | null;
  currentLtp: number | null;
  returnPct: number | null;
  oi: number | null;
  oiChangePct: number | null;
  volume: number | null;
  iv: number | null;
  delta: number | null;
  theta: number | null;
  gamma: number | null;
  vega: number | null;
  daysToExpiry: number | null;
};

const NEW_LISTING_MAX_BARS = 45;

export async function getOverview(): Promise<Overview> {
  const empty: Overview = { lastScanDate: null, lastScanStatus: null, activeCount: 0, trackedCount: 0, newListingCount: 0 };
  if (!sql) return empty;
  try {
    const [scan] = await sql`SELECT trade_date, status FROM scan_runs ORDER BY trade_date DESC, id DESC LIMIT 1`;
    const [{ active }] = await sql`SELECT count(*)::int AS active FROM instruments WHERE active = TRUE`;
    const [{ tracked }] = await sql`SELECT count(*)::int AS tracked FROM tracker_entries WHERE status = 'active'`;
    const [{ newcount }] = await sql`
      SELECT count(*)::int AS newcount FROM (
        SELECT i.id FROM instruments i JOIN price_history p ON p.instrument_id = i.id
        WHERE i.active = TRUE GROUP BY i.id HAVING count(p.id) < ${NEW_LISTING_MAX_BARS}
      ) t`;
    return {
      lastScanDate: scan?.trade_date ?? null,
      lastScanStatus: scan?.status ?? null,
      activeCount: active ?? 0,
      trackedCount: tracked ?? 0,
      newListingCount: newcount ?? 0,
    };
  } catch (e) {
    console.error("getOverview failed:", e);
    return empty;
  }
}

export async function getStrategyMetrics(): Promise<Metric[]> {
  if (!sql) return [];
  try {
    const rows = await sql`
      SELECT s.key, s.display_name, m.horizon_days, m.sample_size, m.hit_rate, m.base_rate,
             m.excess_hit_rate, m.expectancy, m.avg_win, m.avg_loss
      FROM strategies s
      LEFT JOIN strategy_metrics m ON m.strategy_id = s.id
      WHERE s.active = TRUE
      ORDER BY s.display_name`;
    return rows.map((r) => ({
      key: r.key,
      displayName: r.display_name,
      horizonDays: r.horizon_days ?? 100,
      sampleSize: r.sample_size ?? 0,
      hitRate: num(r.hit_rate),
      baseRate: num(r.base_rate),
      excessHitRate: num(r.excess_hit_rate),
      expectancy: num(r.expectancy),
      avgWin: num(r.avg_win),
      avgLoss: num(r.avg_loss),
    }));
  } catch (e) {
    console.error("getStrategyMetrics failed:", e);
    return [];
  }
}

export async function getLatestSignals(): Promise<Signal[]> {
  if (!sql) return [];
  try {
    const rows = await sql`
      SELECT i.nse_symbol, i.symbol_name, i.exchange_pref, st.display_name AS strategy,
             sg.close, sg.rsi, sg.volume_ratio, sg.candle_type, sg.trade_date
      FROM scan_signals sg
      JOIN instruments i ON i.id = sg.instrument_id
      JOIN strategies st ON st.id = sg.strategy_id
      WHERE sg.trade_date = (SELECT max(trade_date) FROM scan_signals)
      ORDER BY sg.volume_ratio DESC NULLS LAST
      LIMIT 200`;
    return rows.map((r) => ({
      symbol: r.nse_symbol ?? r.symbol_name,
      name: r.symbol_name,
      exchange: r.exchange_pref,
      strategy: r.strategy,
      close: num(r.close),
      rsi: num(r.rsi),
      volumeRatio: num(r.volume_ratio),
      candleType: r.candle_type,
      tradeDate: r.trade_date,
    }));
  } catch (e) {
    console.error("getLatestSignals failed:", e);
    return [];
  }
}

export async function getTrackerEntries(): Promise<TrackerRow[]> {
  if (!sql) return [];
  try {
    const rows = await sql`
      SELECT t.instrument_id, i.nse_symbol, i.symbol_name, i.exchange_pref, st.display_name AS strategy,
             t.first_seen_date, t.entry_close, t.appearance_count, t.status,
             o.return_vs_close, o.trading_day_n, o.close AS current_close
      FROM tracker_entries t
      JOIN instruments i ON i.id = t.instrument_id
      JOIN strategies st ON st.id = t.strategy_id
      LEFT JOIN LATERAL (
        SELECT return_vs_close, trading_day_n, close FROM tracker_observations
        WHERE tracker_entry_id = t.id ORDER BY trade_date DESC LIMIT 1
      ) o ON TRUE
      ORDER BY t.first_seen_date DESC, i.nse_symbol
      LIMIT 3000`;
    return rows.map((r) => ({
      instrumentId: r.instrument_id,
      symbol: r.nse_symbol ?? r.symbol_name,
      name: r.symbol_name,
      exchange: r.exchange_pref,
      strategy: r.strategy,
      firstSeenDate: r.first_seen_date,
      entryClose: num(r.entry_close),
      currentClose: num(r.current_close),
      appearanceCount: r.appearance_count ?? 1,
      status: r.status,
      latestReturn: num(r.return_vs_close),
      dayN: r.trading_day_n ?? null,
    }));
  } catch (e) {
    console.error("getTrackerEntries failed:", e);
    return [];
  }
}

// Tracker rows (same shape/columns as getTrackerEntries) but only for starred instruments —
// powers the Starred page with the identical TrackerView layout.
export async function getStarredTracker(): Promise<TrackerRow[]> {
  if (!sql) return [];
  try {
    const rows = await sql`
      SELECT t.instrument_id, i.nse_symbol, i.symbol_name, i.exchange_pref, st.display_name AS strategy,
             t.first_seen_date, t.entry_close, t.appearance_count, t.status,
             o.return_vs_close, o.trading_day_n, o.close AS current_close
      FROM tracker_entries t
      JOIN starred sr ON sr.instrument_id = t.instrument_id
      JOIN instruments i ON i.id = t.instrument_id
      JOIN strategies st ON st.id = t.strategy_id
      LEFT JOIN LATERAL (
        SELECT return_vs_close, trading_day_n, close FROM tracker_observations
        WHERE tracker_entry_id = t.id ORDER BY trade_date DESC LIMIT 1
      ) o ON TRUE
      ORDER BY t.first_seen_date DESC, i.nse_symbol
      LIMIT 3000`;
    return rows.map((r) => ({
      instrumentId: r.instrument_id,
      symbol: r.nse_symbol ?? r.symbol_name,
      name: r.symbol_name,
      exchange: r.exchange_pref,
      strategy: r.strategy,
      firstSeenDate: r.first_seen_date,
      entryClose: num(r.entry_close),
      currentClose: num(r.current_close),
      appearanceCount: r.appearance_count ?? 1,
      status: r.status,
      latestReturn: num(r.return_vs_close),
      dayN: r.trading_day_n ?? null,
    }));
  } catch {
    return []; // starred / tracker tables may not exist yet
  }
}

export async function getNewListings(): Promise<NewListing[]> {
  if (!sql) return [];
  try {
    const rows = await sql`
      SELECT i.id AS instrument_id, i.nse_symbol, i.symbol_name, i.exchange_pref,
             count(p.id)::int AS bars,
             min(p.trade_date) AS first_bar,
             (array_agg(p.close ORDER BY p.trade_date ASC))[1] AS first_close,
             (array_agg(p.close ORDER BY p.trade_date DESC))[1] AS last_close
      FROM instruments i
      JOIN price_history p ON p.instrument_id = i.id
      WHERE i.active = TRUE
      GROUP BY i.id
      HAVING count(p.id) < ${NEW_LISTING_MAX_BARS}
      ORDER BY min(p.trade_date) DESC, count(p.id) ASC
      LIMIT 1000`;
    return rows.map((r) => {
      const first = num(r.first_close);
      const last = num(r.last_close);
      return {
        instrumentId: r.instrument_id,
        symbol: r.nse_symbol ?? r.symbol_name,
        name: r.symbol_name,
        exchange: r.exchange_pref,
        bars: r.bars,
        firstSeen: r.first_bar,
        entryClose: first,
        currentClose: last,
        returnPct: first && last ? last / first - 1 : null,
      };
    });
  } catch (e) {
    console.error("getNewListings failed:", e);
    return [];
  }
}

export async function getStarredIds(): Promise<number[]> {
  if (!sql) return [];
  try {
    const rows = await sql`SELECT instrument_id FROM starred`;
    return rows.map((r) => r.instrument_id as number);
  } catch {
    return []; // table may not exist until the first star is added
  }
}

export async function getOptionTracker(): Promise<OptionRow[]> {
  if (!sql) return [];
  try {
    const rows = await sql`
      SELECT t.contract_id, c.underlying_symbol, c.exchange, c.instrument_type, c.expiry_date,
             c.strike, c.option_type, c.lot_size, t.first_seen_date, t.entry_ltp,
             o.ltp AS current_ltp, o.return_vs_entry, o.oi, o.oi_change_pct, o.volume,
             o.iv, o.delta, o.theta, o.gamma, o.vega, o.days_to_expiry
      FROM option_tracker t
      JOIN option_contracts c ON c.id = t.contract_id
      LEFT JOIN LATERAL (
        SELECT ltp, return_vs_entry, oi, oi_change_pct, volume, iv, delta, theta, gamma, vega, days_to_expiry
        FROM option_observations WHERE tracker_id = t.id ORDER BY trade_date DESC LIMIT 1
      ) o ON TRUE
      WHERE t.status = 'active'
      ORDER BY t.first_seen_date DESC, c.underlying_symbol, c.strike
      LIMIT 5000`;
    return rows.map((r) => ({
      contractId: r.contract_id,
      underlying: r.underlying_symbol,
      exchange: r.exchange,
      instrumentType: r.instrument_type,
      expiry: r.expiry_date,
      strike: num(r.strike),
      optionType: r.option_type,
      lotSize: r.lot_size ?? null,
      firstSeen: r.first_seen_date,
      entryLtp: num(r.entry_ltp),
      currentLtp: num(r.current_ltp),
      returnPct: num(r.return_vs_entry),
      oi: num(r.oi),
      oiChangePct: num(r.oi_change_pct),
      volume: num(r.volume),
      iv: num(r.iv),
      delta: num(r.delta),
      theta: num(r.theta),
      gamma: num(r.gamma),
      vega: num(r.vega),
      daysToExpiry: r.days_to_expiry ?? null,
    }));
  } catch (e) {
    // option_* tables may not exist until the first catalog refresh / option scan runs
    return [];
  }
}

export async function getStarred(): Promise<StarredRow[]> {
  if (!sql) return [];
  try {
    const rows = await sql`
      SELECT i.id AS instrument_id, i.nse_symbol, i.symbol_name, i.exchange_pref,
             (SELECT close FROM price_history WHERE instrument_id = i.id ORDER BY trade_date DESC LIMIT 1) AS last_close
      FROM starred s
      JOIN instruments i ON i.id = s.instrument_id
      ORDER BY s.created_at DESC`;
    return rows.map((r) => ({
      instrumentId: r.instrument_id,
      symbol: r.nse_symbol ?? r.symbol_name,
      name: r.symbol_name,
      exchange: r.exchange_pref,
      lastClose: num(r.last_close),
    }));
  } catch {
    return [];
  }
}

export type StorageTable = {
  name: string;
  totalBytes: number;
  totalPretty: string;
  heapPretty: string;
  indexesPretty: string;
  rows: number | null;
};

export type Storage = {
  ok: boolean;
  usedBytes: number;
  usedPretty: string;
  capBytes: number;
  tables: StorageTable[];
};

// Neon Free plan storage allowance: 0.5 GB per project (current as of 2026).
const NEON_FREE_CAP_BYTES = 536_870_912;

export async function getStorage(): Promise<Storage> {
  const empty: Storage = { ok: false, usedBytes: 0, usedPretty: "—", capBytes: NEON_FREE_CAP_BYTES, tables: [] };
  if (!sql) return empty;
  try {
    const [tot] = await sql`
      SELECT pg_database_size(current_database()) AS bytes,
             pg_size_pretty(pg_database_size(current_database())) AS pretty`;
    const rows = await sql`
      SELECT t.relname AS table_name,
             pg_total_relation_size(c.oid) AS total_bytes,
             pg_size_pretty(pg_total_relation_size(c.oid)) AS total_pretty,
             pg_size_pretty(pg_relation_size(c.oid)) AS heap_pretty,
             pg_size_pretty(pg_indexes_size(c.oid)) AS indexes_pretty,
             t.n_live_tup AS rows_live,
             c.reltuples::bigint AS rows_planner
      FROM pg_stat_user_tables t
      JOIN pg_class c ON c.oid = (quote_ident(t.schemaname) || '.' || quote_ident(t.relname))::regclass
      ORDER BY pg_total_relation_size(c.oid) DESC
      LIMIT 8`;
    return {
      ok: true,
      usedBytes: Number(tot?.bytes ?? 0),
      usedPretty: tot?.pretty ?? "—",
      capBytes: NEON_FREE_CAP_BYTES,
      tables: rows.map((r) => {
        const live = Number(r.rows_live ?? 0);
        const planner = Number(r.rows_planner ?? 0);
        return {
          name: r.table_name as string,
          totalBytes: Number(r.total_bytes ?? 0),
          totalPretty: (r.total_pretty as string) ?? "—",
          heapPretty: (r.heap_pretty as string) ?? "—",
          indexesPretty: (r.indexes_pretty as string) ?? "—",
          rows: live > 0 ? live : planner > 0 ? planner : 0,
        };
      }),
    };
  } catch (e) {
    console.error("getStorage failed:", e);
    return empty;
  }
}
