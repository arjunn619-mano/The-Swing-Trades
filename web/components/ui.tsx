import Link from "next/link";
import { chartUrl, pct } from "@/lib/format";

export function ChartLink({ exchange, ticker }: { exchange: string | null; ticker: string | null }) {
  const url = chartUrl(exchange, ticker);
  if (!url) return <span className="text-slate-600">—</span>;
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      title="Open chart on TradingView"
      className="text-slate-400 hover:text-slate-200"
    >
      ↗
    </a>
  );
}

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-navy-700/60 bg-navy-900/70 p-4 shadow-sm ${className}`}>
      {children}
    </div>
  );
}

export function StatCard({ label, value, hint, href }: { label: string; value: React.ReactNode; hint?: string; href?: string }) {
  const inner = (
    <Card className={href ? "h-full transition-colors hover:border-navy-700 hover:bg-navy-900" : ""}>
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-slate-100">{value}</div>
      {hint ? <div className="mt-0.5 text-xs text-slate-500">{hint}</div> : null}
    </Card>
  );
  return href ? <Link href={href} className="block">{inner}</Link> : inner;
}

export function SectionHeading({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-3">
      <h2 className="text-lg font-semibold text-slate-100">{title}</h2>
      {subtitle ? <p className="text-sm text-slate-400">{subtitle}</p> : null}
    </div>
  );
}

export function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <Card className="border-dashed text-center text-sm text-slate-400">{children}</Card>
  );
}

export function Badge({ children, tone = "slate" }: { children: React.ReactNode; tone?: "slate" | "green" | "red" | "amber" | "blue" }) {
  const tones: Record<string, string> = {
    slate: "bg-slate-700/40 text-slate-300",
    green: "bg-emerald-500/15 text-emerald-300",
    red: "bg-rose-500/15 text-rose-300",
    amber: "bg-amber-500/15 text-amber-300",
    blue: "bg-sky-500/15 text-sky-300",
  };
  return <span className={`inline-block rounded-md px-1.5 py-0.5 text-xs font-medium ${tones[tone]}`}>{children}</span>;
}

export function ReturnBadge({ value }: { value: number | null }) {
  if (value === null || Number.isNaN(value)) return <span className="text-slate-500">—</span>;
  const tone = value > 0 ? "green" : value < 0 ? "red" : "slate";
  const sign = value > 0 ? "+" : "";
  return <Badge tone={tone}>{sign}{pct(value)}</Badge>;
}

type Column<T> = {
  key: string;
  label: string;
  align?: "left" | "right";
  render: (row: T) => React.ReactNode;
};

export function DataTable<T>({ columns, rows, empty }: { columns: Column<T>[]; rows: T[]; empty: string }) {
  if (rows.length === 0) return <EmptyState>{empty}</EmptyState>;
  return (
    <div className="overflow-x-auto rounded-xl border border-navy-700/60 bg-navy-900/40">
      <table className="w-full min-w-[640px] text-sm">
        <thead>
          <tr className="bg-navy-900/70 text-left text-xs uppercase tracking-wide text-slate-400">
            {columns.map((c) => (
              <th key={c.key} className={`whitespace-nowrap px-3 py-2 font-medium ${c.align === "right" ? "text-right" : ""}`}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-t border-navy-700/40 hover:bg-navy-800/40">
              {columns.map((c) => (
                <td key={c.key} className={`whitespace-nowrap px-3 py-2 ${c.align === "right" ? "text-right tabular-nums" : ""}`}>
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Disclaimer() {
  return (
    <footer className="mx-auto mt-10 max-w-[1800px] px-4 pb-24 text-xs text-slate-500 sm:px-6 md:pb-10">
      <Card className="bg-navy-900/40">
        <p className="font-medium text-slate-400">What is this?</p>
        <p className="mt-1">
          An end-of-day screener that scans the NSE/BSE equity universe each evening and tracks every
          qualifying stock for 100 trading days, then measures whether each strategy beats the market
          (hit rate vs. base rate). It is a <span className="text-slate-300">research and observation tool</span>.
        </p>
        <p className="mt-2 text-slate-600">
          For personal research and educational purposes only. Not investment advice. No buy/sell
          recommendation is implied.
        </p>
      </Card>
    </footer>
  );
}
