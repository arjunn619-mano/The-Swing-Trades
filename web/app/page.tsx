import { Badge, ChartLink, DataTable, ReturnBadge, SectionHeading, StatCard } from "@/components/ui";
import { dateStr, fixed, money, pct } from "@/lib/format";
import { getLatestSignals, getOverview, getStrategyMetrics, type Metric, type Signal } from "@/lib/queries";

export const revalidate = 300; // ISR: serve cached, refresh every 5 min (visitors hit the CDN, not the DB)

export default async function Home() {
  const [overview, metrics, signals] = await Promise.all([
    getOverview(),
    getStrategyMetrics(),
    getLatestSignals(),
  ]);

  return (
    <div className="space-y-8">
      <section>
        <div className="flex items-center gap-2">
          <h1 className="text-xl font-semibold text-slate-100">Overview</h1>
          {overview.lastScanStatus ? (
            <Badge tone={overview.lastScanStatus === "success" ? "green" : "amber"}>{overview.lastScanStatus}</Badge>
          ) : null}
        </div>
        <p className="mt-1 text-sm text-slate-400">
          Last successful scan: <span className="text-slate-200">{dateStr(overview.lastScanDate)}</span>
        </p>
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard label="Universe" value={overview.activeCount.toLocaleString("en-IN")} hint="active equities" />
          <StatCard label="Tracked" value={overview.trackedCount.toLocaleString("en-IN")} hint="active entries" href="/tracker" />
          <StatCard label="New listings" value={overview.newListingCount.toLocaleString("en-IN")} hint="< 45 days history" href="/new-listings" />
          <StatCard label="Strategies" value={metrics.length} hint="screening logics" href="/strategies" />
        </div>
      </section>

      <section>
        <SectionHeading
          title="Strategy edge"
          subtitle="Hit rate shown next to the market base rate — edge is the excess, not the raw rate."
        />
        <DataTable<Metric>
          rows={metrics}
          empty="No strategy metrics yet — they populate as tracked stocks accumulate outcomes."
          columns={[
            { key: "name", label: "Strategy", render: (m) => <span className="font-medium text-slate-100">{m.displayName}</span> },
            { key: "hit", label: "Hit rate", align: "right", render: (m) => <ReturnBadge value={m.hitRate} /> },
            { key: "base", label: "Base rate", align: "right", render: (m) => <span className="text-slate-300">{m.baseRate === null ? "—" : pct(m.baseRate)}</span> },
            { key: "excess", label: "Excess (edge)", align: "right", render: (m) => <ReturnBadge value={m.excessHitRate} /> },
            { key: "exp", label: "Expectancy", align: "right", render: (m) => <ReturnBadge value={m.expectancy} /> },
            { key: "n", label: "Sample", align: "right", render: (m) => <span className="text-slate-300">{m.sampleSize}</span> },
            { key: "h", label: "Horizon", align: "right", render: (m) => <span className="text-slate-500">{m.horizonDays}d</span> },
          ]}
        />
      </section>

      <section>
        <SectionHeading
          title="Latest signals"
          subtitle={signals.length ? `${signals.length} stock(s) qualified on ${dateStr(signals[0].tradeDate)}` : "Most recent scan"}
        />
        <DataTable<Signal>
          rows={signals}
          empty="No signals on the most recent scan. Many days produce few or none — expected for a selective screener."
          columns={[
            { key: "sym", label: "Symbol", render: (s) => <span className="font-semibold text-slate-100">{s.symbol}</span> },
            { key: "name", label: "Name", render: (s) => <span className="text-slate-400">{s.name}</span> },
            { key: "strat", label: "Strategy", render: (s) => <span className="text-slate-300">{s.strategy}</span> },
            { key: "close", label: "Close", align: "right", render: (s) => <span className="text-slate-200">{money(s.close)}</span> },
            { key: "rsi", label: "RSI", align: "right", render: (s) => fixed(s.rsi, 1) },
            { key: "vol", label: "Vol×", align: "right", render: (s) => `${fixed(s.volumeRatio, 2)}×` },
            { key: "candle", label: "Candle", render: (s) => (s.candleType ? <Badge tone="green">{s.candleType.replace(/_/g, " ")}</Badge> : "—") },
            { key: "chart", label: "Chart", align: "right", render: (s) => <ChartLink exchange={s.exchange} ticker={s.symbol} /> },
          ]}
        />
      </section>
    </div>
  );
}
