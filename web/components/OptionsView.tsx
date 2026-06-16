"use client";

import { useMemo, useState } from "react";
import { ChartLink } from "@/components/ui";
import { dateStr, fixed, money, pct } from "@/lib/format";
import type { OptionRow } from "@/lib/queries";

type SortKey =
  | "underlying" | "strike" | "expiry" | "daysToExpiry" | "entryLtp" | "currentLtp"
  | "returnPct" | "iv" | "delta" | "oi" | "volume";
type ReturnFilter = "all" | "positive" | "negative";
type TypeFilter = "all" | "CE" | "PE";

const COLUMNS: { key: SortKey | "type" | "theta" | "gamma" | "vega" | "oiChangePct" | "chart"; label: string; align?: "right"; sortable?: boolean }[] = [
  { key: "underlying", label: "Underlying", sortable: true },
  { key: "strike", label: "Strike", align: "right", sortable: true },
  { key: "type", label: "C/P" },
  { key: "expiry", label: "Expiry", sortable: true },
  { key: "daysToExpiry", label: "Days", align: "right", sortable: true },
  { key: "entryLtp", label: "Entry", align: "right", sortable: true },
  { key: "currentLtp", label: "Now", align: "right", sortable: true },
  { key: "returnPct", label: "Return", align: "right", sortable: true },
  { key: "iv", label: "IV", align: "right", sortable: true },
  { key: "delta", label: "Δ", align: "right", sortable: true },
  { key: "theta", label: "θ", align: "right" },
  { key: "gamma", label: "γ", align: "right" },
  { key: "vega", label: "ν", align: "right" },
  { key: "oi", label: "OI", align: "right", sortable: true },
  { key: "oiChangePct", label: "OI Δ%", align: "right" },
  { key: "volume", label: "Vol", align: "right", sortable: true },
  { key: "chart", label: "Chart", align: "right" },
];

const SORT_OPTIONS = COLUMNS.filter((c) => c.sortable).map((c) => ({ key: c.key as SortKey, label: c.label }));

function value(r: OptionRow, key: SortKey): number | string {
  switch (key) {
    case "underlying": return r.underlying ?? "";
    case "expiry": return r.expiry ?? "";
    case "strike": return r.strike ?? -Infinity;
    case "daysToExpiry": return r.daysToExpiry ?? -Infinity;
    case "entryLtp": return r.entryLtp ?? -Infinity;
    case "currentLtp": return r.currentLtp ?? -Infinity;
    case "returnPct": return r.returnPct ?? -Infinity;
    case "iv": return r.iv ?? -Infinity;
    case "delta": return r.delta ?? -Infinity;
    case "oi": return r.oi ?? -Infinity;
    case "volume": return r.volume ?? -Infinity;
    default: return "";
  }
}

const intFmt = (x: number | null) => (x === null || Number.isNaN(x) ? "—" : Number(x).toLocaleString("en-IN"));
const strikeFmt = (x: number | null) => (x === null || Number.isNaN(x) ? "—" : Number(x).toLocaleString("en-IN"));

function ReturnCell({ value: v }: { value: number | null }) {
  if (v === null || Number.isNaN(v)) return <span className="text-slate-500">—</span>;
  const tone = v > 0 ? "bg-emerald-500/15 text-emerald-300" : v < 0 ? "bg-rose-500/15 text-rose-300" : "bg-slate-700/40 text-slate-300";
  return <span className={`rounded-md px-1.5 py-0.5 text-xs font-medium ${tone}`}>{v > 0 ? "+" : ""}{pct(v)}</span>;
}

function TypeBadge({ t }: { t: string }) {
  const tone = t === "CE" ? "bg-sky-500/15 text-sky-300" : "bg-amber-500/15 text-amber-300";
  return <span className={`rounded-md px-1.5 py-0.5 text-xs font-semibold ${tone}`}>{t}</span>;
}

export function OptionsView({ rows }: { rows: OptionRow[] }) {
  const [underlying, setUnderlying] = useState<string>("all");
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [expiry, setExpiry] = useState<string>("all");
  const [returnFilter, setReturnFilter] = useState<ReturnFilter>("all");
  const [sortKey, setSortKey] = useState<SortKey>("returnPct");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const underlyingCounts = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of rows) m.set(r.underlying, (m.get(r.underlying) ?? 0) + 1);
    return m;
  }, [rows]);
  const underlyings = useMemo(() => Array.from(underlyingCounts.keys()).sort(), [underlyingCounts]);
  const expiries = useMemo(() => Array.from(new Set(rows.map((r) => r.expiry))).sort(), [rows]);

  const scoped = useMemo(() => {
    let out = rows;
    if (underlying !== "all") out = out.filter((r) => r.underlying === underlying);
    if (typeFilter !== "all") out = out.filter((r) => r.optionType === typeFilter);
    if (expiry !== "all") out = out.filter((r) => r.expiry === expiry);
    return out;
  }, [rows, underlying, typeFilter, expiry]);

  const positives = scoped.filter((r) => (r.returnPct ?? 0) > 0).length;
  const positivePct = scoped.length ? positives / scoped.length : 0;

  const filtered = useMemo(() => {
    let out = scoped;
    if (returnFilter === "positive") out = out.filter((r) => (r.returnPct ?? 0) > 0);
    else if (returnFilter === "negative") out = out.filter((r) => (r.returnPct ?? 0) < 0);
    return [...out].sort((a, b) => {
      const va = value(a, sortKey);
      const vb = value(b, sortKey);
      const c = typeof va === "string" && typeof vb === "string" ? va.localeCompare(vb) : (va as number) - (vb as number);
      return sortDir === "asc" ? c : -c;
    });
  }, [scoped, returnFilter, sortKey, sortDir]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(key); setSortDir("desc"); }
  }

  if (rows.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-navy-700/60 bg-navy-900/40 p-4 text-center text-sm text-slate-400">
        No option contracts tracked yet. A contract is added the first day its volume clears 1 lakh — entries appear after the option scan runs.
      </div>
    );
  }

  const sidebarItems = [
    { key: "all", label: "All underlyings", count: rows.length },
    ...underlyings.map((u) => ({ key: u, label: u, count: underlyingCounts.get(u) ?? 0 })),
  ];
  const typeTabs: { key: TypeFilter; label: string }[] = [
    { key: "all", label: "All" },
    { key: "CE", label: "Calls" },
    { key: "PE", label: "Puts" },
  ];
  const returnTabs: { key: ReturnFilter; label: string }[] = [
    { key: "all", label: "All" },
    { key: "positive", label: "Positive" },
    { key: "negative", label: "Negative" },
  ];

  return (
    <div className="flex flex-col gap-4 lg:flex-row">
      {/* Underlying filter — horizontal chips on mobile, vertical sidebar on desktop */}
      <aside className="lg:w-56 lg:shrink-0">
        <div className="mb-2 hidden text-xs uppercase tracking-wide text-slate-400 lg:block">Underlying</div>
        <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 lg:mx-0 lg:max-h-[70vh] lg:flex-col lg:gap-1 lg:overflow-y-auto lg:px-0 lg:pb-0 [scrollbar-width:thin] [&::-webkit-scrollbar]:h-0">
          {sidebarItems.map((item) => (
            <button
              key={item.key}
              onClick={() => setUnderlying(item.key)}
              className={`flex shrink-0 items-center gap-2 whitespace-nowrap rounded-md px-3 py-2 text-left text-sm transition-colors lg:w-full lg:justify-between lg:shrink ${
                underlying === item.key ? "bg-navy-700 text-white" : "bg-navy-900/60 text-slate-300 hover:bg-navy-800 lg:bg-transparent"
              }`}
            >
              <span className="truncate">{item.label}</span>
              <span className={`text-xs ${underlying === item.key ? "text-slate-300" : "text-slate-500"}`}>{item.count}</span>
            </button>
          ))}
        </div>
      </aside>

      <div className="min-w-0 flex-1 space-y-3">
        {/* Controls */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3 text-sm">
            <span className="text-slate-400">
              {filtered.length.toLocaleString("en-IN")} of {scoped.length.toLocaleString("en-IN")}
            </span>
            <span className="rounded-md bg-navy-800 px-2 py-1 text-xs text-slate-300">
              <span className="font-semibold text-emerald-300">{(positivePct * 100).toFixed(1)}%</span> positive
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {/* Expiry */}
            <select
              value={expiry}
              onChange={(e) => setExpiry(e.target.value)}
              className="rounded-md border border-navy-700/60 bg-navy-900 px-2 py-1 text-xs text-slate-200"
              aria-label="Expiry"
            >
              <option value="all">All expiries</option>
              {expiries.map((e) => (
                <option key={e} value={e}>{dateStr(e)}</option>
              ))}
            </select>
            {/* Mobile sort control */}
            <div className="flex items-center gap-1 md:hidden">
              <select
                value={sortKey}
                onChange={(e) => setSortKey(e.target.value as SortKey)}
                className="rounded-md border border-navy-700/60 bg-navy-900 px-2 py-1 text-xs text-slate-200"
                aria-label="Sort by"
              >
                {SORT_OPTIONS.map((o) => (
                  <option key={o.key} value={o.key}>{o.label}</option>
                ))}
              </select>
              <button
                onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}
                className="rounded-md border border-navy-700/60 bg-navy-900 px-2 py-1 text-xs text-slate-300"
                aria-label="Toggle sort direction"
              >
                {sortDir === "asc" ? "▲" : "▼"}
              </button>
            </div>
            {/* Call/Put */}
            <div className="flex gap-0.5 rounded-lg border border-navy-700/60 bg-navy-900/60 p-0.5">
              {typeTabs.map((t) => (
                <button
                  key={t.key}
                  onClick={() => setTypeFilter(t.key)}
                  className={`rounded-md px-2.5 py-1 text-sm transition-colors ${
                    typeFilter === t.key ? "bg-navy-700 text-white" : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
            {/* Return filter */}
            <div className="flex gap-0.5 rounded-lg border border-navy-700/60 bg-navy-900/60 p-0.5">
              {returnTabs.map((t) => (
                <button
                  key={t.key}
                  onClick={() => setReturnFilter(t.key)}
                  className={`rounded-md px-2.5 py-1 text-sm transition-colors ${
                    returnFilter === t.key ? "bg-navy-700 text-white" : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Desktop table */}
        <div className="hidden overflow-x-auto rounded-xl border border-navy-700/60 bg-navy-900/40 md:block">
          <table className="w-full min-w-[1200px] text-sm">
            <thead>
              <tr className="bg-navy-900/70 text-left text-xs uppercase tracking-wide text-slate-400">
                {COLUMNS.map((c) => {
                  const active = Boolean(c.sortable) && c.key === sortKey;
                  return (
                    <th
                      key={c.key}
                      onClick={c.sortable ? () => toggleSort(c.key as SortKey) : undefined}
                      className={`whitespace-nowrap px-3 py-2 font-medium ${c.align === "right" ? "text-right" : ""} ${
                        c.sortable ? "cursor-pointer select-none hover:text-slate-200" : ""
                      }`}
                    >
                      <span className={`inline-flex items-center gap-1 ${c.align === "right" ? "flex-row-reverse" : ""}`}>
                        {c.label}
                        {active ? <span className="text-slate-500">{sortDir === "asc" ? "▲" : "▼"}</span> : null}
                      </span>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {filtered.map((r, i) => (
                <tr key={i} className="border-t border-navy-700/40 hover:bg-navy-800/40">
                  <td className="whitespace-nowrap px-3 py-2 font-semibold text-slate-100">{r.underlying}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-slate-200">{strikeFmt(r.strike)}</td>
                  <td className="whitespace-nowrap px-3 py-2"><TypeBadge t={r.optionType} /></td>
                  <td className="whitespace-nowrap px-3 py-2 text-slate-300">{dateStr(r.expiry)}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-slate-300">{r.daysToExpiry ?? "—"}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-slate-200">{money(r.entryLtp)}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-slate-200">{money(r.currentLtp)}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right"><ReturnCell value={r.returnPct} /></td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-slate-300">{fixed(r.iv, 1)}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-slate-300">{fixed(r.delta, 2)}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-slate-400">{fixed(r.theta, 2)}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-slate-400">{fixed(r.gamma, 4)}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-slate-400">{fixed(r.vega, 2)}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-slate-300">{intFmt(r.oi)}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-slate-400">{r.oiChangePct === null ? "—" : pct(r.oiChangePct)}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-slate-300">{intFmt(r.volume)}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right"><ChartLink exchange={r.exchange} ticker={r.underlying} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Mobile cards */}
        <div className="space-y-2 md:hidden">
          {filtered.map((r, i) => (
            <div key={i} className="rounded-lg border border-navy-700/60 bg-navy-900/40 p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="truncate font-semibold text-slate-100">{r.underlying}</span>
                  <span className="tabular-nums text-slate-300">{strikeFmt(r.strike)}</span>
                  <TypeBadge t={r.optionType} />
                  <ChartLink exchange={r.exchange} ticker={r.underlying} />
                </div>
                <ReturnCell value={r.returnPct} />
              </div>
              <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                <span className="text-slate-500">Expiry <span className="text-slate-300">{dateStr(r.expiry)}</span></span>
                <span className="text-slate-500">Days <span className="text-slate-300">{r.daysToExpiry ?? "—"}</span></span>
                <span className="text-slate-500">Entry <span className="text-slate-300">{money(r.entryLtp)}</span></span>
                <span className="text-slate-500">Now <span className="text-slate-300">{money(r.currentLtp)}</span></span>
                <span className="text-slate-500">IV <span className="text-slate-300">{fixed(r.iv, 1)}</span></span>
                <span className="text-slate-500">Δ <span className="text-slate-300">{fixed(r.delta, 2)}</span></span>
                <span className="text-slate-500">OI <span className="text-slate-300">{intFmt(r.oi)}</span></span>
                <span className="text-slate-500">Vol <span className="text-slate-300">{intFmt(r.volume)}</span></span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
