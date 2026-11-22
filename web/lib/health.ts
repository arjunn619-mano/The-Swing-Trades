import { sql } from "@/lib/db";

// Health + efficiency data. The worker judges every limit when a job ends (worker/swing_trades/utils/health.py) and
// writes ONE job_runs row with limits_json; this file only reads it, so the rules live in one place.

export type HealthState = "ok" | "watch" | "broken" | "none";

export type HealthItem = {
  key: string;
  name: string;
  used: number | null;
  limit: number | null;
  unit: string;
  pct: number | null;
  forecast: number | null;
  forecast_pct: number | null;
  state: HealthState;
  text: string;
  when_hit: string;
  how: string;
};

export type JobRun = {
  job: string;
  started_at: string;
  finished_at: string;
  status: string;
  trade_date: string | null;
  dhan_login: string;
  dhan_login_tries: number;
  dhan_calls: number;
  items: number;
  db_bytes: number | null;
  note: string | null;
};

export type Health = {
  ok: boolean; // false = could not read (shown as such, never as fine)
  logStarted: boolean; // false = table empty / not created yet (before the first logged job)
  state: HealthState;
  judgedAt: string | null;
  judgedBy: string | null;
  items: HealthItem[];
  runs: JobRun[];
};

const RANK: Record<HealthState, number> = { ok: 0, none: 1, watch: 2, broken: 3 };

export function worst(items: HealthItem[]): HealthState {
  return items.reduce<HealthState>((w, i) => (i.state !== "none" && RANK[i.state] > RANK[w] ? i.state : w), "ok");
}

export async function getHealth(): Promise<Health> {
  if (process.env.HEALTH_SAMPLE === "1") return SAMPLE;
  const empty: Health = { ok: false, logStarted: false, state: "none", judgedAt: null, judgedBy: null, items: [], runs: [] };
  if (!sql) return empty;
  try {
    const runs = (await sql`
      SELECT job, started_at, finished_at, status, trade_date, dhan_login, dhan_login_tries, dhan_calls, items,
             db_bytes, note
      FROM job_runs ORDER BY finished_at DESC LIMIT 40`) as unknown as JobRun[];
    const [latest] = await sql`
      SELECT job, finished_at, alarm_state, limits_json FROM job_runs
      WHERE limits_json IS NOT NULL ORDER BY finished_at DESC LIMIT 1`;
    if (!latest) return { ...empty, ok: true, runs };
    const items = (latest.limits_json ?? []) as HealthItem[];
    return {
      ok: true,
      logStarted: true,
      state: (latest.alarm_state as HealthState) ?? worst(items),
      judgedAt: String(latest.finished_at),
      judgedBy: latest.job as string,
      items,
      runs: runs.map((r) => ({ ...r, started_at: String(r.started_at), finished_at: String(r.finished_at) })),
    };
  } catch (e) {
    // job_runs does not exist until the first job applies the new schema: say so, do not pretend it is fine.
    const msg = String((e as Error)?.message ?? e);
    if (msg.includes("job_runs") && msg.includes("does not exist")) return { ...empty, ok: true };
    console.error("getHealth failed:", e);
    return empty;
  }
}

// ── local preview only (HEALTH_SAMPLE=1): realistic numbers, never used in production ─────────────────────────────
const iso = (d: string) => new Date(d).toISOString();
const SAMPLE_ITEMS: HealthItem[] = [
  { key: "scan_fresh", name: "EOD scan", used: null, limit: null, unit: "", pct: null, forecast: null, forecast_pct: null, state: "ok",
    text: "paused on purpose (scan workflow has `if: false`); last scanned session 2026-10-30", when_hit: "no new scan results while paused", how: "" },
  { key: "news_fresh", name: "News capture", used: null, limit: null, unit: "", pct: null, forecast: null, forecast_pct: null, state: "ok",
    text: "last run 22 Nov 16:33, 0 h ago, success, 41 items", when_hit: "news picks stop", how: "" },
  { key: "dhan_login", name: "Dhan login", used: null, limit: null, unit: "", pct: null, forecast: null, forecast_pct: null, state: "ok",
    text: "no login while paused (the scan never logs in)", when_hit: "no data; repeated failures can lock the shared Dhan account", how: "" },
  { key: "scan_runtime", name: "Scan run time", used: 52.5, limit: 360, unit: "min", pct: 14.6, forecast: null, forecast_pct: null, state: "ok",
    text: "last scan took 52 min (17:00-17:52 IST); GitHub stops a job at 6 h", when_hit: "GitHub cancels the scan; that day's results are lost", how: "" },
  { key: "login_slot", name: "Login slot", used: null, limit: null, unit: "", pct: null, forecast: null, forecast_pct: null, state: "broken",
    text: "logged in at Tue 16:20 IST, INSIDE the NIFTY bots' Dhan hours 08:30-16:50", when_hit: "the live bot's Dhan token is cancelled at once (one active token per account)", how: "" },
  { key: "alarm_trial", name: "Telegram alarms", used: null, limit: null, unit: "", pct: null, forecast: null, forecast_pct: null, state: "ok",
    text: "on trial until 2026-12-06: shown here, not sent (new checks prove themselves first)", when_hit: "-", how: "" },
  { key: "neon_storage", name: "Neon storage", used: 331.4, limit: 537, unit: "MB", pct: 61.7, forecast: null, forecast_pct: null, state: "watch",
    text: "331 of 537 MB; growing 1.2 MB/day, red in ~82 days", when_hit: "writes fail (scans stop saving); reads still work", how: "" },
  { key: "neon_compute", name: "Neon compute", used: 6.2, limit: 100, unit: "CU-h", pct: 6.2, forecast: 8.6, forecast_pct: 8.6, state: "ok",
    text: "estimate 6.2 of 100 CU-h this month, month end ~9", when_hit: "database sleeps until next month: scans and the site fail",
    how: "lower bound: 46 job runs x (run time + 5 idle min) at 0.25 CU; website reads not counted; Neon's own meter needs its API key" },
  { key: "gh_minutes", name: "GitHub Actions", used: 1120, limit: null, unit: "min", pct: null, forecast: 1540, forecast_pct: null, state: "ok",
    text: "1120 min this month; free because the repo is public (if made private: month end ~1540 of 2000)", when_hit: "private repo only: all jobs stop until next month", how: "" },
  { key: "dhan_calls", name: "Dhan data calls", used: 41, limit: 100000, unit: "calls/day", pct: 0, forecast: null, forecast_pct: null, state: "ok",
    text: "41 of 100,000 today (Swing Trades only)", when_hit: "Dhan refuses calls for a while (the NIFTY bots share the account)", how: "" },
  { key: "neon_transfer", name: "Neon data read out", used: null, limit: null, unit: "GB", pct: null, forecast: null, forecast_pct: null, state: "none",
    text: "not measured: needs a Neon API key (Arjun)", when_hit: "database locked until next month", how: "" },
  { key: "vercel", name: "Vercel (site)", used: null, limit: null, unit: "", pct: null, forecast: null, forecast_pct: null, state: "none",
    text: "not measured: needs a Vercel token (Arjun); shared with the NIFTY bot site's account", when_hit: "site may be paused until resumed by hand", how: "" },
];
const SAMPLE: Health = {
  ok: true,
  logStarted: true,
  state: "broken",
  judgedAt: iso("2026-11-22T16:33:00+05:30"),
  judgedBy: "news_capture",
  items: SAMPLE_ITEMS,
  runs: [
    ["news_capture", "2026-11-22T16:31:00+05:30", "2026-11-22T16:33:00+05:30", "success", 0, 41, 331_400_000],
    ["eod_scan", "2026-10-28T17:00:30+05:30", "2026-10-28T17:52:30+05:30", "success", 38, 4210, 329_000_000],
    ["eod_scan", "2026-10-27T17:00:30+05:30", "2026-10-27T17:51:00+05:30", "success", 37, 4198, 327_800_000],
    ["eod_scan", "2026-10-26T17:00:30+05:30", "2026-10-26T17:52:40+05:30", "success", 37, 4190, 326_500_000],
    ["eod_scan", "2026-10-23T17:00:30+05:30", "2026-10-23T17:42:40+05:30", "success", 36, 4176, 325_100_000],
    ["eod_scan", "2026-10-25T17:00:30+05:30", "2026-10-25T17:03:10+05:30", "skipped", 0, 0, 325_900_000],
  ].map(([job, s, f, status, calls, items, b]) => ({
    job: job as string, started_at: iso(s as string), finished_at: iso(f as string), status: status as string, trade_date: null,
    dhan_login: job === "eod_scan" && status === "success" ? "ok" : "none", dhan_login_tries: job === "eod_scan" && status === "success" ? 1 : 0,
    dhan_calls: calls as number, items: items as number, db_bytes: b as number, note: null,
  })),
};
