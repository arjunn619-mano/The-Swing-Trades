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
  strategy: string;
  close: number | null;
  rsi: number | null;
  volumeRatio: number | null;
  candleType: string | null;
  tradeDate: string;
};

export type TrackerRow = {
  symbol: string;
  name: string;
  strategy: string;
  firstSeenDate: string;
  entryClose: number | null;
  appearanceCount: number;
  status: string;
  latestReturn: number | null;
  dayN: number | null;
};

export type NewListing = {
  symbol: string;
  name: string;
  exchange: string;
  bars: number;
  firstBar: string;
  lastBar: string;
  lastClose: number | null;
};

const NEW_LISTING_MAX_BARS = 45; // < ~9 trading weeks of history => recently listed

export async function getOverview(): Promise<Overview> {
  const empty: Overview = {
    lastScanDate: null,
    lastScanStatus: null,
    activeCount: 0,
    trackedCount: 0,
    newListingCount: 0,
  };
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
      SELECT i.nse_symbol, i.symbol_name, st.display_name AS strategy,
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
      SELECT i.nse_symbol, i.symbol_name, st.display_name AS strategy,
             t.first_seen_date, t.entry_close, t.appearance_count, t.status,
             o.return_vs_close, o.trading_day_n
      FROM tracker_entries t
      JOIN instruments i ON i.id = t.instrument_id
      JOIN strategies st ON st.id = t.strategy_id
      LEFT JOIN LATERAL (
        SELECT return_vs_close, trading_day_n FROM tracker_observations
        WHERE tracker_entry_id = t.id ORDER BY trade_date DESC LIMIT 1
      ) o ON TRUE
      ORDER BY t.first_seen_date DESC, i.nse_symbol
      LIMIT 3000`;
    return rows.map((r) => ({
      symbol: r.nse_symbol ?? r.symbol_name,
      name: r.symbol_name,
      strategy: r.strategy,
      firstSeenDate: r.first_seen_date,
      entryClose: num(r.entry_close),
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

export async function getNewListings(): Promise<NewListing[]> {
  if (!sql) return [];
  try {
    const rows = await sql`
      SELECT i.nse_symbol, i.symbol_name, i.exchange_pref,
             count(p.id)::int AS bars, min(p.trade_date) AS first_bar, max(p.trade_date) AS last_bar,
             (SELECT close FROM price_history WHERE instrument_id = i.id ORDER BY trade_date DESC LIMIT 1) AS last_close
      FROM instruments i
      JOIN price_history p ON p.instrument_id = i.id
      WHERE i.active = TRUE
      GROUP BY i.id
      HAVING count(p.id) < ${NEW_LISTING_MAX_BARS}
      ORDER BY min(p.trade_date) DESC, count(p.id) ASC
      LIMIT 300`;
    return rows.map((r) => ({
      symbol: r.nse_symbol ?? r.symbol_name,
      name: r.symbol_name,
      exchange: r.exchange_pref,
      bars: r.bars,
      firstBar: r.first_bar,
      lastBar: r.last_bar,
      lastClose: num(r.last_close),
    }));
  } catch (e) {
    console.error("getNewListings failed:", e);
    return [];
  }
}
