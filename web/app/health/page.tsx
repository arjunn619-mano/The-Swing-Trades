import { Badge, Card, SectionHeading } from "@/components/ui";
import { getHealth, type HealthItem, type HealthState, type JobRun } from "@/lib/health";

// ISR: the data changes only when a job ends (a few times a day), so 10 min keeps the DB reads tiny.
export const revalidate = 600;

const TONE: Record<HealthState, "green" | "amber" | "red" | "slate"> = { ok: "green", watch: "amber", broken: "red", none: "slate" };
const LABEL: Record<HealthState, string> = { ok: "OK", watch: "Watch", broken: "Act", none: "Not measured" };
const BAR: Record<HealthState, string> = { ok: "bg-emerald-500", watch: "bg-amber-400", broken: "bg-rose-500", none: "bg-slate-600" };
const RANK: Record<HealthState, number> = { broken: 0, watch: 1, ok: 2, none: 3 };

const ist = (d: string | null, withDate = true) =>
  d
    ? new Intl.DateTimeFormat("en-IN", {
        timeZone: "Asia/Kolkata",
        ...(withDate ? { day: "2-digit", month: "short" } : {}),
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(new Date(d))
    : "—";
const mins = (r: JobRun) => (new Date(r.finished_at).getTime() - new Date(r.started_at).getTime()) / 60000;
const JOB: Record<string, string> = { eod_scan: "EOD scan", news_capture: "News capture" };

function Headline({ state, judgedAt, judgedBy, items }: { state: HealthState; judgedAt: string | null; judgedBy: string | null; items: HealthItem[] }) {
  const red = items.filter((i) => i.state === "broken").length;
  const amber = items.filter((i) => i.state === "watch").length;
  const title = state === "broken" ? "Something needs action" : state === "watch" ? "Something to watch" : "All healthy";
  return (
    <Card className={state === "broken" ? "border-rose-500/40" : state === "watch" ? "border-amber-400/40" : "border-emerald-500/30"}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-base font-semibold text-slate-100">{title}</div>
        <Badge tone={TONE[state]}>{LABEL[state]}</Badge>
      </div>
      <p className="mt-1 text-sm text-slate-400">
        {red} to act on, {amber} to watch, out of {items.filter((i) => i.state !== "none").length} checks. Judged when the{" "}
        {JOB[judgedBy ?? ""] ?? "last job"} ended, {ist(judgedAt)} IST.
      </p>
    </Card>
  );
}

function LimitRow({ i }: { i: HealthItem }) {
  const pct = i.forecast_pct != null && (i.pct == null || i.forecast_pct > i.pct) ? i.forecast_pct : i.pct;
  return (
    <div className="space-y-1.5 border-t border-navy-700/40 py-3 first:border-t-0 first:pt-0 last:pb-0">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-medium text-slate-200">{i.name}</div>
        <Badge tone={TONE[i.state]}>{LABEL[i.state]}</Badge>
      </div>
      {pct != null && i.limit ? (
        <div className="relative h-2 w-full overflow-hidden rounded-full bg-navy-700">
          <div className={`h-full rounded-full ${BAR[i.state]}`} style={{ width: `${Math.min(100, Math.max(pct, 2))}%` }} />
          <div className="absolute inset-y-0 left-[60%] w-px bg-amber-300/60" title="amber at 60%" />
          <div className="absolute inset-y-0 left-[80%] w-px bg-rose-400/70" title="red at 80%" />
        </div>
      ) : null}
      <p className="break-words text-xs text-slate-300">{i.text}</p>
      <p className="text-xs text-slate-500">If it is hit: {i.when_hit}</p>
      {i.how ? <p className="text-xs text-slate-600">{i.how}</p> : null}
    </div>
  );
}

function Efficiency({ runs }: { runs: JobRun[] }) {
  const scans = runs.filter((r) => r.job === "eod_scan" && r.status === "success").slice(0, 10);
  if (!scans.length) {
    return (
      <Card className="text-sm text-slate-400">
        No successful scan logged yet. Speed, cost per stock and database growth per scan appear here from the first logged scan.
      </Card>
    );
  }
  const avg = scans.reduce((s, r) => s + mins(r), 0) / scans.length;
  const longest = Math.max(...scans.map(mins), 1);
  const perMin = scans.reduce((s, r) => s + r.items / Math.max(mins(r), 0.1), 0) / scans.length;
  const calls = scans.reduce((s, r) => s + r.dhan_calls, 0) / scans.length;
  const growth: number[] = [];
  for (let k = 0; k + 1 < runs.length; k++) {
    if (runs[k].job === "eod_scan" && runs[k].status === "success" && runs[k].db_bytes && runs[k + 1].db_bytes)
      growth.push((runs[k].db_bytes! - runs[k + 1].db_bytes!) / 1e6);
  }
  const g = growth.length ? growth.reduce((a, b) => a + b, 0) / growth.length : null;
  const tiles: [string, string, string][] = [
    ["Scan time", `${avg.toFixed(0)} min`, `average of the last ${scans.length}; GitHub stops a job at 6 h`],
    ["Speed", `${perMin.toFixed(0)} stocks/min`, "stocks priced and judged per minute"],
    ["Dhan calls", `${calls.toFixed(0)} per scan`, "of 100,000 a day for the whole account"],
    ["DB growth", g == null ? "—" : `${g.toFixed(1)} MB/scan`, "how fast storage fills"],
  ];
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {tiles.map(([k, v, h]) => (
          <Card key={k}>
            <div className="text-xs uppercase tracking-wide text-slate-400">{k}</div>
            <div className="mt-1 text-xl font-semibold text-slate-100">{v}</div>
            <div className="mt-0.5 text-xs text-slate-500">{h}</div>
          </Card>
        ))}
      </div>
      <Card className="space-y-2">
        <div className="text-xs uppercase tracking-wide text-slate-400">Last scans: minutes taken (longest = full bar)</div>
        {scans.map((r) => {
          const m = mins(r);
          const tone: HealthState = m >= 288 ? "broken" : m >= 216 ? "watch" : "ok"; // 80 % / 60 % of GitHub's 360 min
          return (
            <div key={r.started_at} className="flex items-center gap-2 text-xs">
              <span className="w-14 shrink-0 tabular-nums text-slate-400">{ist(r.started_at).split(",")[0]}</span>
              <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-navy-700">
                <div className={`h-full rounded-full ${BAR[tone]}`} style={{ width: `${Math.min(100, (m / longest) * 100)}%` }} />
              </div>
              <span className="w-12 shrink-0 text-right tabular-nums text-slate-300">{m.toFixed(0)} min</span>
            </div>
          );
        })}
      </Card>
    </div>
  );
}

function Jobs({ runs }: { runs: JobRun[] }) {
  if (!runs.length) return <Card className="text-sm text-slate-400">No job runs logged yet.</Card>;
  return (
    <div className="overflow-x-auto rounded-xl border border-navy-700/60">
      <table className="w-full min-w-[560px] text-xs">
        <thead>
          <tr className="bg-navy-900/70 text-left uppercase tracking-wide text-slate-500">
            {["Job", "Ended (IST)", "Took", "Result", "Items", "Dhan calls", "Login"].map((h) => (
              <th key={h} className="px-3 py-2 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {runs.slice(0, 15).map((r) => (
            <tr key={r.job + r.finished_at} className="border-t border-navy-700/40">
              <td className="px-3 py-1.5 text-slate-200">{JOB[r.job] ?? r.job}</td>
              <td className="px-3 py-1.5 tabular-nums text-slate-300">{ist(r.finished_at)}</td>
              <td className="px-3 py-1.5 tabular-nums text-slate-300">{mins(r).toFixed(0)} min</td>
              <td className="px-3 py-1.5">
                <Badge tone={r.status === "success" ? "green" : r.status === "failed" ? "red" : "slate"}>{r.status}</Badge>
              </td>
              <td className="px-3 py-1.5 tabular-nums text-slate-300">{r.items.toLocaleString("en-IN")}</td>
              <td className="px-3 py-1.5 tabular-nums text-slate-300">{r.dhan_calls}</td>
              <td className="px-3 py-1.5 text-slate-300">
                {r.dhan_login === "none" ? "—" : `${r.dhan_login} (${r.dhan_login_tries} try)`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function HealthPage() {
  const h = await getHealth();
  const items = [...h.items].sort((a, b) => RANK[a.state] - RANK[b.state]);
  return (
    <div className="space-y-6">
      <SectionHeading
        title="Health"
        subtitle="Is every job working, and how close is each outside service (Neon, GitHub, Dhan, Vercel) to its free limit? Amber at 60%, red at 80%, now or by month end."
      />

      {!h.ok ? (
        <Card className="text-sm text-slate-400">Couldn&apos;t read the health log right now. Showing nothing rather than a false &ldquo;healthy&rdquo;.</Card>
      ) : !h.logStarted ? (
        <Card className="text-sm text-slate-400">
          The health log starts with the next job run (the daily news capture at ~16:30 IST). Until then nothing is judged.
        </Card>
      ) : (
        <Headline state={h.state} judgedAt={h.judgedAt} judgedBy={h.judgedBy} items={h.items} />
      )}

      <Card className="space-y-1 text-sm text-slate-300">
        <div className="text-xs uppercase tracking-wide text-slate-400">How you get alarms</div>
        <p>
          <span className="text-slate-100">Telegram</span>, in the same chat as the scan-failure alerts: one message when the overall state
          changes (to amber, to red, or back to normal), so a standing problem is not repeated every run. New checks run two
          weeks on trial first: shown here, not sent, so a wrong check cannot flood your phone.
        </p>
        <p>
          <span className="text-slate-100">This page</span>, updated whenever a job ends. The NIFTY bots&apos; Health page also shows a
          Swing Trades row from this page&apos;s data.
        </p>
      </Card>

      {h.logStarted ? (
        <section>
          <SectionHeading title="Checks and outside limits" subtitle="Worst first. A limit we cannot measure yet says why, and is never shown as fine." />
          <Card>
            {items.map((i) => (
              <LimitRow key={i.key} i={i} />
            ))}
          </Card>
        </section>
      ) : null}

      <section>
        <SectionHeading title="Efficiency" subtitle="How long the scan takes, how much it does per minute, and what it costs the free limits." />
        <Efficiency runs={h.runs} />
      </section>

      <section>
        <SectionHeading title="Recent job runs" subtitle="Worked, not just ran: result, items written and the Dhan login for each run." />
        <Jobs runs={h.runs} />
      </section>
    </div>
  );
}
